"""API tests for task lifecycle, conflict handling and persistence."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import ADMIN


def _start(test_client: TestClient, project_id: str, instruction: str):
    return test_client.post(
        "/api/tasks", json={"project_id": project_id, "instruction": instruction}
    )


def test_task_runs_to_completion_with_events(authed, make_project, wait_for_terminal):
    project = make_project(authed)
    response = _start(authed, project["id"], "add a health endpoint")
    assert response.status_code == 201
    task = response.json()
    assert task["task_type"] == "CODING"

    final = wait_for_terminal(authed, task["id"])
    assert final["status"] == "COMPLETED"
    assert final["result_summary"]
    assert final["completed_at"] is not None

    detail = authed.get(f"/api/tasks/{task['id']}").json()
    assert len(detail["files"]) == 1
    assert detail["files"][0]["change_type"] == "modified"

    events = authed.get(f"/api/tasks/{task['id']}/events").json()
    types = [event["type"] for event in events]
    for expected in (
        "task.created",
        "run.started",
        "file.changed",
        "test.result",
        "run.finished",
        "task.status_changed",
    ):
        assert expected in types, types


def test_conflicting_task_is_rejected(slow_authed, make_project):
    project = make_project(slow_authed)
    assert _start(slow_authed, project["id"], "fix bug one").status_code == 201
    conflict = _start(slow_authed, project["id"], "fix bug two")
    assert conflict.status_code == 409
    assert "active" in conflict.json()["detail"]


def test_cancel_requests_then_confirms(slow_authed, make_project, wait_for_terminal):
    project = make_project(slow_authed)
    task = _start(slow_authed, project["id"], "refactor everything").json()

    cancelled = slow_authed.post(f"/api/tasks/{task['id']}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] in ("CANCEL_REQUESTED", "CANCELLED")

    final = wait_for_terminal(slow_authed, task["id"])
    assert final["status"] == "CANCELLED"


def test_steer_active_task(slow_authed, make_project, wait_for_terminal):
    project = make_project(slow_authed)
    task = _start(slow_authed, project["id"], "build the feature").json()

    steered = slow_authed.post(
        f"/api/tasks/{task['id']}/steer", json={"instruction": "also update the docs"}
    )
    assert steered.status_code == 200

    final = wait_for_terminal(slow_authed, task["id"])
    assert final["status"] == "COMPLETED"

    events = slow_authed.get(f"/api/tasks/{task['id']}/events").json()
    assert any(event["data"].get("steered") for event in events)


def test_steering_an_inactive_task_conflicts(authed, make_project, wait_for_terminal):
    project = make_project(authed)
    task = _start(authed, project["id"], "quick task").json()
    wait_for_terminal(authed, task["id"])
    response = authed.post(
        f"/api/tasks/{task['id']}/steer", json={"instruction": "too late"}
    )
    assert response.status_code == 409


def test_unknown_task_and_project_errors(authed, make_project):
    assert authed.get("/api/tasks/nope").status_code == 404
    assert authed.post("/api/tasks/nope/cancel").status_code == 404
    assert _start(authed, "missing-project", "do it").status_code == 404


def test_tasks_can_be_filtered_by_project(authed, make_project, wait_for_terminal):
    first = make_project(authed, "alpha")
    second = make_project(authed, "beta")
    task_a = _start(authed, first["id"], "add alpha feature").json()
    wait_for_terminal(authed, task_a["id"])

    listed = authed.get("/api/tasks", params={"project_id": first["id"]}).json()
    assert [task["id"] for task in listed] == [task_a["id"]]
    assert authed.get("/api/tasks", params={"project_id": second["id"]}).json() == []


def test_task_state_survives_restart(settings_factory, wait_for_terminal):
    settings = settings_factory()
    with TestClient(create_app(settings)) as first_runner:
        first_runner.post("/api/auth/setup", json=ADMIN)
        project = first_runner.post("/api/projects", json={"name": "persist"}).json()
        task = _start(first_runner, project["id"], "persist me").json()
        wait_for_terminal(first_runner, task["id"])

    # A brand new process/app instance over the same data directory.
    with TestClient(create_app(settings)) as second_runner:
        assert second_runner.post("/api/auth/login", json=ADMIN).status_code == 200
        tasks = second_runner.get("/api/tasks").json()
        assert [t["id"] for t in tasks] == [task["id"]]
        assert tasks[0]["status"] == "COMPLETED"
        events = second_runner.get(f"/api/tasks/{task['id']}/events").json()
        assert any(event["type"] == "run.finished" for event in events)
