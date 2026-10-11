"""Tests for static checks (Pyright) and the Pi / Orchestrator API surface."""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.domain import CheckOutcome
from app.main import create_app
from app.services.checks import ChecksService, find_python_files
from tests.conftest import ADMIN

def _find_pyright() -> str | None:
    """Locate pyright without depending on the ambient PATH.

    The backend installs pyright into the project virtualenv, which is not on
    PATH for a bare `../venv/bin/python -m pytest`. Resolving it explicitly
    means the pyright tests actually run instead of silently skipping.
    """
    found = shutil.which("pyright")
    if found:
        return found
    candidate = Path(__file__).resolve().parents[2] / "venv" / "bin" / "pyright"
    return str(candidate) if candidate.is_file() else None


PYRIGHT = _find_pyright()
requires_pyright = pytest.mark.skipif(PYRIGHT is None, reason="pyright is not installed")


# --------------------------------------------------------------------------- #
# Checks service
# --------------------------------------------------------------------------- #
def test_status_reports_a_missing_tool(settings_factory):
    service = ChecksService(settings_factory(pyright_executable="definitely-not-pyright"))
    status = service.status()
    assert status["available"] is False
    assert "pip install pyright" in status["detail"]


def test_find_python_files_skips_vendor_and_hidden_directories(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "mod.py").write_text("x = 1")
    (tmp_path / "script.py").write_text("y = 2")
    for ignored in ("venv", "node_modules", "__pycache__", ".venv", ".solo"):
        directory = tmp_path / ignored
        directory.mkdir()
        (directory / "noise.py").write_text("z = 3")

    found = find_python_files(tmp_path)
    assert sorted(found) == ["pkg/mod.py", "script.py"]


@requires_pyright
async def test_checks_are_skipped_without_python(tmp_path, settings_factory):
    """The reason must be "no Python files", not "the tool is missing"."""
    root = tmp_path / "repo"
    root.mkdir()
    (root / "README.md").write_text("# nothing to check")

    service = ChecksService(settings_factory(pyright_executable=PYRIGHT))
    result = await service.run_for_project(root)
    assert result.outcome == CheckOutcome.SKIPPED.value
    assert "No Python files" in result.summary


async def test_checks_are_skipped_when_disabled(tmp_path, settings_factory):
    root = tmp_path / "repo"
    root.mkdir()
    (root / "mod.py").write_text("x = 1")
    service = ChecksService(settings_factory(checks_enabled=False))
    result = await service.run_for_project(root)
    assert result.outcome == CheckOutcome.SKIPPED.value
    assert "disabled" in result.summary


async def test_checks_report_a_missing_pyright_gracefully(tmp_path, settings_factory):
    root = tmp_path / "repo"
    root.mkdir()
    (root / "mod.py").write_text("x = 1")
    service = ChecksService(settings_factory(pyright_executable="definitely-not-pyright"))
    result = await service.run_for_project(root)
    assert result.outcome == CheckOutcome.SKIPPED.value
    assert "not installed" in result.summary


@requires_pyright
async def test_pyright_finds_a_real_type_error(tmp_path, settings_factory):
    root = tmp_path / "repo"
    root.mkdir()
    (root / "bad.py").write_text(
        "def greet(name: str) -> str:\n    return 'hi ' + name\n\n\ngreet(123)\n"
    )

    service = ChecksService(
        settings_factory(pyright_executable=PYRIGHT, pyright_timeout_seconds=120)
    )
    result = await service.run_for_project(root)

    assert result.outcome == CheckOutcome.FAILED.value
    assert result.error_count >= 1
    assert result.passed is False
    assert result.diagnostics
    assert result.diagnostics[0].file == "bad.py"
    assert result.diagnostics[0].line >= 1


@requires_pyright
async def test_pyright_passes_on_clean_code(tmp_path, settings_factory):
    root = tmp_path / "repo"
    root.mkdir()
    (root / "good.py").write_text("def greet(name: str) -> str:\n    return f'hi {name}'\n")

    service = ChecksService(
        settings_factory(pyright_executable=PYRIGHT, pyright_timeout_seconds=120)
    )
    result = await service.run_for_project(root)
    assert result.outcome == CheckOutcome.PASSED.value
    assert result.passed is True


@requires_pyright
async def test_pyright_prefers_the_changed_files(tmp_path, settings_factory):
    root = tmp_path / "repo"
    root.mkdir()
    (root / "clean.py").write_text("x: int = 1\n")
    (root / "broken.py").write_text("y: int = 'not an int'\n")

    service = ChecksService(
        settings_factory(pyright_executable=PYRIGHT, pyright_timeout_seconds=120)
    )
    result = await service.run_for_project(root, changed_files=["clean.py"])
    # Only the requested file is checked, so the failure in broken.py is absent.
    assert result.files_checked == 1
    assert result.error_count == 0


def test_check_result_serialises_for_the_api(tmp_path, settings_factory):
    from app.services.checks import CheckResult, Diagnostic

    result = CheckResult(
        tool="pyright",
        outcome=CheckOutcome.FAILED.value,
        summary="1 error",
        error_count=1,
        diagnostics=[Diagnostic(file="a.py", line=1, column=2, severity="error", message="boom")],
    )
    payload = result.to_dict()
    assert payload["passed"] is False
    assert payload["diagnostics"][0]["file"] == "a.py"


# --------------------------------------------------------------------------- #
# API fixtures
# --------------------------------------------------------------------------- #
@pytest.fixture
def pi_client(pi_settings_factory):
    with TestClient(create_app(pi_settings_factory())) as client:
        response = client.post("/api/auth/setup", json=ADMIN)
        assert response.status_code == 201
        yield client


@pytest.fixture
def pi_authed(pi_client):
    return pi_client


# --------------------------------------------------------------------------- #
# /api/pi
# --------------------------------------------------------------------------- #
def test_pi_status_reports_the_runtime_and_backend(pi_authed):
    body = pi_authed.get("/api/pi/status").json()
    assert body["backend"] == "pi"
    assert body["runtime"]["available"] is True
    assert body["runtime"]["version"] == "1.1.0-fake"
    assert body["minimal_harness"] is True
    assert body["approve_project"] is False
    assert body["auth_file"].endswith("auth.json")


def test_pi_status_requires_authentication(client):
    assert client.get("/api/pi/status").status_code == 401


def test_pi_providers_come_from_pi_and_the_curated_list(pi_authed):
    providers = pi_authed.get("/api/pi/providers").json()
    ids = {item["id"] for item in providers}
    # A provider discovered from Pi's catalog…
    assert "fake" in ids
    # …and providers offered even without a catalog (manual fallback).
    assert "anthropic" in ids
    assert "openrouter" in ids
    openrouter = next(item for item in providers if item["id"] == "openrouter")
    assert openrouter["env_var"] == "OPENROUTER_API_KEY"


def test_saving_and_removing_a_credential_writes_pis_auth_file(pi_authed):
    settings = pi_authed.app.state.container.settings
    auth_file = Path(settings.pi_agent_dir) / "auth.json"

    response = pi_authed.put(
        "/api/pi/providers/anthropic/credential",
        json={"api_key": "sk-ant-test-value-123456"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ready"] is True
    assert body["status"] == "ready"

    # Written through Pi's own mechanism, with restrictive permissions.
    assert auth_file.is_file()
    stored = json.loads(auth_file.read_text())
    assert stored["anthropic"]["type"] == "api_key"
    assert stored["anthropic"]["key"] == "sk-ant-test-value-123456"
    assert (auth_file.stat().st_mode & 0o077) == 0

    # The key is never returned by any endpoint.
    assert "sk-ant-test-value-123456" not in pi_authed.get("/api/pi/status").text
    assert "sk-ant-test-value-123456" not in pi_authed.get("/api/pi/providers").text

    removed = pi_authed.delete("/api/pi/providers/anthropic/credential")
    assert removed.status_code == 200
    assert "anthropic" not in json.loads(auth_file.read_text())
    assert pi_authed.delete("/api/pi/providers/anthropic/credential").status_code == 404


def test_reusing_the_orchestrator_key_requires_one_first(pi_authed):
    response = pi_authed.post(
        "/api/pi/providers/openrouter/credential/from-orchestrator"
    )
    assert response.status_code == 400
    assert "Orchestrator" in response.json()["detail"]


def test_reusing_the_orchestrator_key_copies_it_into_pis_store(pi_authed):
    pi_authed.put(
        "/api/settings", json={"openrouter_api_key": "sk-or-v1-orchestrator-key"}
    )
    response = pi_authed.post(
        "/api/pi/providers/openrouter/credential/from-orchestrator"
    )
    assert response.status_code == 200
    assert response.json()["ready"] is True

    settings = pi_authed.app.state.container.settings
    stored = json.loads((Path(settings.pi_agent_dir) / "auth.json").read_text())
    assert stored["openrouter"]["key"] == "sk-or-v1-orchestrator-key"


def test_provider_auth_check_explains_not_ready(pi_authed):
    body = pi_authed.get("/api/pi/providers/unconfigured-provider/auth").json()
    assert body["ready"] is False
    assert body["reason"] == "credentials_not_configured"


def test_provider_models_are_discovered_from_pi(pi_authed):
    models = pi_authed.get("/api/pi/models").json()
    ids = {model["id"] for model in models}
    assert {"fake-model", "second-model"} <= ids
    filtered = pi_authed.get("/api/pi/models", params={"provider": "nothing"}).json()
    assert filtered == []


def test_catalog_refresh_runs_the_pi_command(pi_authed):
    body = pi_authed.post("/api/pi/models/refresh").json()
    assert body["ok"] is True
    assert "refreshed" in body["message"].lower()


def test_provider_test_never_claims_verification_without_a_real_request(pi_authed):
    """`deep=false` only proves a credential is present."""
    pi_authed.put("/api/pi/providers/anthropic/credential", json={"api_key": "sk-ant-x"})
    body = pi_authed.post("/api/pi/providers/anthropic/test").json()
    assert body["ok"] is True
    assert body["state"] == "configured"
    assert "real request" in body["message"]


def test_provider_test_reports_missing_credentials(pi_authed):
    body = pi_authed.post("/api/pi/providers/unconfigured-provider/test").json()
    assert body["ok"] is False
    assert body["state"] == "not_configured"


def test_provider_test_requires_a_model_for_a_deep_check(pi_authed):
    pi_authed.put("/api/pi/providers/anthropic/credential", json={"api_key": "sk-ant-x"})
    body = pi_authed.post(
        "/api/pi/providers/anthropic/test", params={"deep": True}
    ).json()
    assert body["ok"] is False
    assert "model" in body["message"].lower()


# --------------------------------------------------------------------------- #
# /api/orchestrator
# --------------------------------------------------------------------------- #
def test_orchestrator_status_is_unconfigured_by_default(pi_authed):
    body = pi_authed.get("/api/orchestrator/status").json()
    assert body["has_key"] is False
    assert body["configured"] is False
    assert body["key_masked"] is None


def test_orchestrator_status_masks_the_key(pi_authed):
    pi_authed.put(
        "/api/settings",
        json={"openrouter_api_key": "sk-or-v1-1234567890abcdef", "openrouter_model": "vendor/model"},
    )
    body = pi_authed.get("/api/orchestrator/status").json()
    assert body["has_key"] is True
    assert body["configured"] is True
    assert body["model"] == "vendor/model"
    assert body["key_masked"].endswith("cdef")
    assert "sk-or-v1-1234567890abcdef" not in json.dumps(body)


def test_orchestrator_config_can_select_a_model(pi_authed):
    body = pi_authed.put(
        "/api/orchestrator/config", json={"model": "vendor/chosen", "enabled": True}
    ).json()
    assert body["model"] == "vendor/chosen"
    assert pi_authed.get("/api/settings").json()["openrouter_model"] == "vendor/chosen"


def test_orchestrator_models_require_a_key(pi_authed):
    response = pi_authed.get("/api/orchestrator/models")
    assert response.status_code == 400
    assert "OpenRouter API key" in response.json()["detail"]


def test_orchestrator_test_without_a_key_is_not_configured(pi_authed):
    body = pi_authed.post("/api/orchestrator/test").json()
    assert body["ok"] is False
    assert body["state"] == "not_configured"


def test_orchestrator_endpoints_require_authentication(client):
    assert client.get("/api/orchestrator/status").status_code == 401
    assert client.get("/api/orchestrator/models").status_code == 401


# --------------------------------------------------------------------------- #
# Orchestration state API
# --------------------------------------------------------------------------- #
def test_orchestration_state_starts_empty(pi_authed, make_project):
    project = make_project(pi_authed, "orch-demo")
    body = pi_authed.get(f"/api/projects/{project['id']}/orchestration").json()
    assert body["summary"]["queue_size"] == 0
    assert body["state"]["project_id"] == project["id"]


def test_notes_are_recorded_through_the_api(pi_authed, make_project):
    project = make_project(pi_authed, "notes-demo")
    body = pi_authed.post(
        f"/api/projects/{project['id']}/orchestration/notes",
        json={"instruction": "remember to update the changelog"},
    ).json()
    assert body["summary"]["pending_notes"] == 1
    assert body["state"]["notes"][0]["text"] == "remember to update the changelog"


def test_plan_without_an_orchestrator_model_returns_no_steps(pi_authed, make_project):
    project = make_project(pi_authed, "plan-demo")
    body = pi_authed.post(
        f"/api/projects/{project['id']}/orchestration/plan",
        json={"instruction": "add a module and tests"},
    ).json()
    # No OpenRouter key is configured, so the deterministic path is used.
    assert body["summary"]["queue_size"] == 0


def test_queue_items_can_be_skipped_and_removed(pi_authed, make_project):
    """Queue mutations via the API, seeded directly in the project store."""
    project = make_project(pi_authed, "queue-demo")
    settings = pi_authed.app.state.container.settings
    state_file = (
        settings.workspaces_dir / project["slug"] / ".solo" / "state" / "orchestration.json"
    )
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(
        json.dumps(
            {
                "version": 1,
                "project_id": project["id"],
                "revision": 1,
                "active_task_id": None,
                "active_plan_id": None,
                "queue": [
                    {"id": "p1", "title": "one", "instruction": "do one", "priority": 10, "status": "pending", "depends_on": []},
                    {"id": "p2", "title": "two", "instruction": "do two", "priority": 20, "status": "pending", "depends_on": []},
                ],
                "notes": [],
            }
        )
    )

    body = pi_authed.post(
        f"/api/projects/{project['id']}/orchestration/queue/p1/skip"
    ).json()
    assert {item["id"]: item["status"] for item in body["state"]["queue"]}["p1"] == "skipped"

    body = pi_authed.delete(
        f"/api/projects/{project['id']}/orchestration/queue/p2"
    ).json()
    assert [item["id"] for item in body["state"]["queue"]] == ["p1"]

    assert (
        pi_authed.delete(f"/api/projects/{project['id']}/orchestration/queue/nope").status_code
        == 404
    )


def test_advance_reports_when_the_queue_is_empty(pi_authed, make_project):
    project = make_project(pi_authed, "advance-demo")
    body = pi_authed.post(f"/api/projects/{project['id']}/orchestration/advance").json()
    assert body["started"] is False
    assert "empty" in body["reason"]


def test_orchestration_endpoints_require_a_project(pi_authed):
    assert pi_authed.get("/api/projects/nope/orchestration").status_code == 404
    assert (
        pi_authed.post("/api/projects/nope/orchestration/notes", json={"instruction": "x"}).status_code
        == 404
    )
    assert pi_authed.post("/api/projects/nope/orchestration/advance").status_code == 404


def test_checks_status_endpoint(pi_authed):
    body = pi_authed.get("/api/checks/status").json()
    assert body["tool"] == "pyright"
    # checks_enabled is False in the fake-Pi settings fixture.
    assert body["enabled"] is False


def test_run_checks_reports_why_it_cannot(pi_authed, make_project):
    project = make_project(pi_authed, "checks-demo")
    response = pi_authed.post(f"/api/projects/{project['id']}/checks")
    assert response.status_code == 409
    assert "detail" in response.json()


def test_every_coding_task_is_tracked_in_the_orchestration_state(
    pi_authed, make_project, wait_for_terminal
):
    """Task management works even without the orchestrator model."""
    project = make_project(pi_authed, "tracking-demo")
    task = pi_authed.post(
        "/api/tasks",
        json={"project_id": project["id"], "instruction": "create hello_world.py"},
    ).json()

    settings = pi_authed.app.state.container.settings
    state_file = (
        settings.workspaces_dir / project["slug"] / ".solo" / "state" / "orchestration.json"
    )
    wait_for_terminal(pi_authed, task["id"])
    assert state_file.is_file(), "orchestration state was not persisted"

    # Marking the plan step is post-settle work: it deliberately runs *after*
    # the terminal status is broadcast, so poll briefly for it to land.
    deadline = time.monotonic() + 5
    body = pi_authed.get(f"/api/projects/{project['id']}/orchestration").json()
    while time.monotonic() < deadline:
        body = pi_authed.get(f"/api/projects/{project['id']}/orchestration").json()
        if body["state"]["queue"][0]["status"] != "running":
            break
        time.sleep(0.05)

    queue = body["state"]["queue"]
    assert len(queue) == 1
    assert queue[0]["task_id"] == task["id"]
    assert queue[0]["status"] == "done"
    assert body["state"]["active_task_id"] is None
    assert body["summary"]["status_counts"]["done"] == 1


def test_chat_reports_how_the_message_was_classified(pi_authed, make_project):
    """The UI can tell whether the orchestrator model or the rules decided."""
    project = make_project(pi_authed, "classify-demo")
    body = pi_authed.post(
        f"/api/projects/{project['id']}/messages",
        json={"content": "how many files are there?"},
    ).json()
    assert body["classified_by"] == "rules"
    assert body["intent"] == "CHAT_OR_EXPLAIN"
