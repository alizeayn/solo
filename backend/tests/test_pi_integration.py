"""Pi integration tests: RPC transport, event translation and the adapter.

These use `tests/fixtures/fake_pi`, a stand-in that speaks the documented JSONL
protocol. That makes the whole integration testable deterministically — no
network, no model, no credentials — while still exercising real subprocesses,
real pipes, real framing and real correlation.

The one thing a fake cannot prove is that a *model* responds. That is covered by
`test_pi_live.py`, which is skipped unless credentials are available.
"""

from __future__ import annotations

import asyncio
import json
import os
import stat
from pathlib import Path

import pytest

from app.adapters.pi_agent import PiCodingAgentAdapter
from app.adapters.pi_events import PiEventTranslator, summarise_test_output
from app.adapters.pi_rpc import PiRpcClient, PiRpcError, PiTimeoutError
from app.adapters.pi_session import PiLaunchConfig, build_pi_argv
from app.config import Settings
from app.domain import EventType

FIXTURE = Path(__file__).parent / "fixtures" / "fake_pi"


@pytest.fixture
def fake_pi() -> str:
    assert FIXTURE.is_file(), "the fake_pi fixture is missing"
    mode = FIXTURE.stat().st_mode
    FIXTURE.chmod(mode | stat.S_IXUSR)
    return str(FIXTURE)


def pi_settings(tmp_path: Path, fake_pi: str, **overrides) -> Settings:
    values = {
        "app_data_dir": tmp_path / "data",
        "agent_backend": "pi",
        "pi_executable": fake_pi,
        "pi_run_timeout_seconds": 60,
        "checks_enabled": False,
        "mock_step_delay": 0.0,
        "log_level": "WARNING",
    }
    values.update(overrides)
    settings = Settings(**values)
    settings.ensure_directories()
    return settings


def client_for(fake_pi: str, cwd: str, mode: str = "success", on_event=None) -> PiRpcClient:
    return PiRpcClient(
        [fake_pi, "--mode", "rpc"],
        cwd=cwd,
        env={"FAKE_PI_MODE": mode},
        on_event=on_event,
        label="fake-pi",
    )


# --------------------------------------------------------------------------- #
# Transport
# --------------------------------------------------------------------------- #
async def test_client_starts_correlates_and_shuts_down(fake_pi, tmp_path):
    client = client_for(fake_pi, str(tmp_path))
    await client.start()
    try:
        assert client.alive

        first = await client.call({"id": "req-1", "type": "get_state"})
        second = await client.call({"id": "req-2", "type": "get_session_stats"})

        # Responses are correlated by id, not by order.
        assert first["model"]["id"] == "fake-model"
        assert second["toolCalls"] == 2
        assert "isStreaming" in first
    finally:
        await client.close(grace=5)

    assert not client.alive
    assert client.exit_code is not None


async def test_bash_command_streams_and_returns_a_result(fake_pi, tmp_path):
    client = client_for(fake_pi, str(tmp_path))
    await client.start()
    try:
        data = await client.call(
            {"id": "b1", "type": "bash", "command": "echo hello"}, timeout=20
        )
        assert data["exitCode"] == 0
        assert "fake-bash-output" in data["output"]
    finally:
        await client.close(grace=5)


async def test_unknown_command_raises_a_pi_error(fake_pi, tmp_path):
    client = client_for(fake_pi, str(tmp_path))
    await client.start()
    try:
        with pytest.raises(PiRpcError, match="unsupported command"):
            await client.call({"type": "definitely_not_a_command"}, timeout=20)
    finally:
        await client.close(grace=5)


async def test_accept_failure_returns_the_raw_response(fake_pi, tmp_path):
    client = client_for(fake_pi, str(tmp_path))
    await client.start()
    try:
        response = await client.call(
            {"type": "definitely_not_a_command"}, timeout=20, accept_failure=True
        )
        assert response["success"] is False
        assert "unsupported command" in response["error"]
    finally:
        await client.close(grace=5)


async def test_malformed_records_do_not_break_the_stream(fake_pi, tmp_path):
    """A non-JSON line must be skipped, not fatal (framing is LF-only)."""
    records: list[dict] = []
    client = client_for(fake_pi, str(tmp_path), mode="garbage", on_event=records.append)
    await client.start()
    try:
        await client.call({"id": "p", "type": "prompt", "message": "go"}, timeout=30)
        await client.wait_for(
            lambda r: r.get("type") == "agent_settled", timeout=30, description="settle"
        )
    finally:
        await client.close(grace=5)
    assert any(r.get("type") == "agent_settled" for r in records)


async def test_timeout_is_reported_clearly(fake_pi, tmp_path):
    client = client_for(fake_pi, str(tmp_path))
    await client.start()
    try:
        with pytest.raises(PiTimeoutError, match="did not answer"):
            await client.call({"type": "get_state"}, timeout=0.001)
    finally:
        await client.close(grace=5)


async def test_unicode_line_separator_inside_json_is_preserved(fake_pi, tmp_path):
    """U+2028 inside a JSON string is valid and must not split a record."""
    records: list[dict] = []
    client = client_for(fake_pi, str(tmp_path), on_event=records.append)
    await client.start()
    try:
        message = "line one\u2028line two\u2029done"
        await client.call({"id": "p", "type": "prompt", "message": message}, timeout=30)
        await client.wait_for(
            lambda r: r.get("type") == "agent_settled", timeout=30, description="settle"
        )
    finally:
        await client.close(grace=5)
    # If the reader had split on the Unicode separators, parsing would have
    # failed and no user message would have been observed intact.
    user_messages = [
        r["message"]["content"]
        for r in records
        if r.get("type") == "message_end" and (r.get("message") or {}).get("role") == "user"
    ]
    assert message in user_messages


async def test_missing_executable_is_reported(fake_pi, tmp_path):
    from app.adapters.pi_rpc import PiUnavailableError

    client = PiRpcClient(["/nonexistent/pi-binary"], cwd=str(tmp_path))
    with pytest.raises(PiUnavailableError, match="was not found"):
        await client.start()


def test_build_pi_argv_reflects_configuration():
    argv = build_pi_argv(
        ["/opt/node", "/opt/pi/cli.js"],
        PiLaunchConfig(
            provider="openrouter",
            model="vendor/model",
            thinking_level="high",
            approve_project=True,
            minimal_harness=True,
        ),
    )
    # The runtime prefix is an absolute interpreter + script, never a bare "pi".
    assert argv[:2] == ["/opt/node", "/opt/pi/cli.js"]
    assert "--mode" in argv and "rpc" in argv
    assert "--no-session" in argv
    # Trust is explicit so behaviour never depends on a saved decision.
    assert "--approve" in argv
    assert "--no-extensions" in argv
    assert ["--provider", "openrouter"] == argv[argv.index("--provider") : argv.index("--provider") + 2]
    assert "--model" in argv and "vendor/model" in argv
    assert "--thinking" in argv and "high" in argv


def test_build_pi_argv_defaults_to_no_approve_and_minimal_harness():
    argv = build_pi_argv(["/opt/node", "/opt/pi/cli.js"], PiLaunchConfig())
    assert "--no-approve" in argv
    assert "--no-extensions" in argv
    assert "--no-skills" in argv
    assert "--provider" not in argv


# --------------------------------------------------------------------------- #
# Event translation
# --------------------------------------------------------------------------- #
def test_thinking_blocks_are_never_forwarded():
    translator = PiEventTranslator(cwd="/proj")
    translator.handle({"type": "message_start", "message": {"role": "assistant"}})
    translator.handle(
        {
            "type": "message_update",
            "assistantMessageEvent": {"type": "thinking_delta", "delta": "secret reasoning"},
        }
    )
    translator.handle(
        {
            "type": "message_update",
            "assistantMessageEvent": {"type": "text_delta", "delta": "public answer"},
        }
    )
    events = translator.handle(
        {"type": "message_end", "message": {"role": "assistant", "stopReason": "stop"}}
    )
    assert [event.message for event in events] == ["public answer"]
    assert all("secret reasoning" not in event.message for event in events)


def test_file_paths_are_reported_relative_to_the_project():
    translator = PiEventTranslator(cwd="/proj")
    events = translator.handle(
        {
            "type": "tool_execution_start",
            "toolCallId": "c1",
            "toolName": "write",
            "args": {"file_path": "/proj/src/pkg/mod.py"},
        }
    )
    assert events[0].type == EventType.FILE_CHANGED.value
    assert events[0].data["path"] == "src/pkg/mod.py"
    assert events[0].data["change_type"] == "written"


def test_paths_outside_the_project_are_left_absolute():
    translator = PiEventTranslator(cwd="/proj")
    events = translator.handle(
        {
            "type": "tool_execution_start",
            "toolCallId": "c1",
            "toolName": "edit",
            "args": {"path": "/elsewhere/file.py"},
        }
    )
    assert events[0].data["path"] == "/elsewhere/file.py"


def test_bash_test_commands_produce_test_results():
    translator = PiEventTranslator(cwd="/proj")
    translator.handle(
        {
            "type": "tool_execution_start",
            "toolCallId": "c1",
            "toolName": "bash",
            "args": {"command": "python3 -m pytest -q"},
        }
    )
    events = translator.handle(
        {
            "type": "tool_execution_end",
            "toolCallId": "c1",
            "toolName": "bash",
            "result": {"content": [{"type": "text", "text": "3 passed, 1 failed in 0.4s"}]},
            "isError": False,
        }
    )
    assert events[0].type == EventType.TEST_RESULT.value
    assert "3 passed" in events[0].message


def test_provider_errors_become_error_events():
    translator = PiEventTranslator(cwd="/proj")
    events = translator.handle(
        {
            "type": "message_end",
            "message": {
                "role": "assistant",
                "stopReason": "error",
                "errorMessage": '{"message":"Insufficient credits","code":402}',
            },
        }
    )
    assert events[0].type == EventType.ERROR.value
    assert "Insufficient credits" in events[0].message
    assert translator.build_result().ok is False


def test_retry_and_compaction_are_summarised_not_narrated_verbatim():
    translator = PiEventTranslator(cwd="/proj")
    retry = translator.handle(
        {"type": "auto_retry_start", "attempt": 1, "maxAttempts": 3, "delayMs": 2000}
    )
    compaction = translator.handle({"type": "compaction_start", "reason": "threshold"})
    assert retry[0].type == EventType.PROGRESS_SUMMARY.value
    assert "retrying (1/3)" in retry[0].message
    assert compaction[0].type == EventType.PROGRESS_SUMMARY.value


def test_settled_marks_the_run_finished():
    translator = PiEventTranslator(cwd="/proj")
    events = translator.handle({"type": "agent_settled", "aborted": False})
    assert events[0].type == EventType.RUN_FINISHED.value
    assert translator.settled is True


def test_summarise_test_output_extracts_counts():
    assert summarise_test_output("noise\n== 3 passed, 1 failed in 0.4s ==\n") == (
        "== 3 passed, 1 failed in 0.4s =="
    )
    assert summarise_test_output("nothing interesting") is None


# --------------------------------------------------------------------------- #
# Adapter
# --------------------------------------------------------------------------- #
async def _loader_factory(config: PiLaunchConfig):
    async def loader() -> PiLaunchConfig:
        return config

    return loader


async def test_adapter_runs_a_task_and_reports_real_file_changes(fake_pi, tmp_path):
    settings = pi_settings(tmp_path, fake_pi)
    work = tmp_path / "project"
    work.mkdir()
    adapter = PiCodingAgentAdapter(
        settings,
        config_loader=await _loader_factory(PiLaunchConfig(provider="fake", model="fake-model")),
    )
    await adapter.start()
    events = []

    async def on_event(event):
        events.append(event)

    try:
        result = await adapter.run(
            task_id="t1", prompt="Create hello_world.py", cwd=str(work), on_event=on_event
        )
    finally:
        await adapter.stop()

    assert result.ok is True
    assert result.cancelled is False
    assert (work / "hello_world.py").is_file()
    assert "Hello World" in (work / "hello_world.py").read_text()

    kinds = [event.type for event in events]
    assert EventType.RUN_STARTED.value in kinds
    assert EventType.FILE_CHANGED.value in kinds
    assert EventType.TEST_RESULT.value in kinds
    assert EventType.ASSISTANT_MESSAGE.value in kinds
    assert EventType.RUN_FINISHED.value in kinds
    assert [e.data.get("path") for e in events if e.type == EventType.FILE_CHANGED.value] == [
        "hello_world.py"
    ]


async def test_adapter_reports_provider_errors_truthfully(fake_pi, tmp_path):
    settings = pi_settings(tmp_path, fake_pi, mock_step_delay=0.0)
    work = tmp_path / "project"
    work.mkdir()
    adapter = PiCodingAgentAdapter(
        settings,
        config_loader=await _loader_factory(PiLaunchConfig(provider="fake", model="fake-model")),
    )
    # The fake reads this to choose behaviour.
    os.environ["FAKE_PI_MODE"] = "error"
    events = []
    try:
        result = await adapter.run(
            task_id="t2",
            prompt="do something",
            cwd=str(work),
            on_event=lambda event: _collect(events, event),
        )
    finally:
        os.environ.pop("FAKE_PI_MODE", None)
        await adapter.stop()

    assert result.ok is False
    assert result.error and "Insufficient credits" in result.error
    assert any(event.type == EventType.ERROR.value for event in events)


async def _collect(bucket, event):
    bucket.append(event)


async def test_adapter_reports_a_missing_model_clearly(fake_pi, tmp_path):
    settings = pi_settings(tmp_path, fake_pi)
    work = tmp_path / "project"
    work.mkdir()
    adapter = PiCodingAgentAdapter(
        settings, config_loader=await _loader_factory(PiLaunchConfig())
    )
    os.environ["FAKE_PI_MODE"] = "no_model"
    events = []
    try:
        result = await adapter.run(
            task_id="t3",
            prompt="anything",
            cwd=str(work),
            on_event=lambda event: _collect(events, event),
        )
    finally:
        os.environ.pop("FAKE_PI_MODE", None)
        await adapter.stop()

    assert result.ok is False
    assert "no model selected" in result.summary.lower()
    assert any(e.data.get("reason") == "no_model" for e in events)


async def test_adapter_survives_a_process_crash(fake_pi, tmp_path):
    settings = pi_settings(tmp_path, fake_pi)
    work = tmp_path / "project"
    work.mkdir()
    adapter = PiCodingAgentAdapter(
        settings, config_loader=await _loader_factory(PiLaunchConfig(model="fake-model"))
    )
    os.environ["FAKE_PI_MODE"] = "crash"
    try:
        result = await adapter.run(
            task_id="t4",
            prompt="crash please",
            cwd=str(work),
            on_event=lambda event: _collect([], event),
        )
    finally:
        os.environ.pop("FAKE_PI_MODE", None)
        await adapter.stop()

    assert result.ok is False
    assert result.error


async def test_adapter_cancellation_is_confirmed_not_assumed(fake_pi, tmp_path):
    settings = pi_settings(tmp_path, fake_pi)
    work = tmp_path / "project"
    work.mkdir()
    adapter = PiCodingAgentAdapter(
        settings, config_loader=await _loader_factory(PiLaunchConfig(model="fake-model"))
    )
    os.environ["FAKE_PI_MODE"] = "cancel"
    try:
        run = asyncio.create_task(
            adapter.run(
                task_id="t5",
                prompt="long job",
                cwd=str(work),
                on_event=lambda event: _collect([], event),
            )
        )
        await asyncio.sleep(0.4)
        await adapter.cancel(task_id="t5")
        result = await asyncio.wait_for(run, timeout=20)
    finally:
        os.environ.pop("FAKE_PI_MODE", None)
        await adapter.stop()

    assert result.cancelled is True
    assert result.ok is False


async def test_adapter_health_reports_a_fake_runtime(fake_pi, tmp_path):
    settings = pi_settings(tmp_path, fake_pi)
    adapter = PiCodingAgentAdapter(settings)
    health = await adapter.health()
    assert health["backend"] == "pi"
    # `--version` is unsupported by the fake, so the adapter must still report a
    # coherent status rather than raising.
    assert "installed" in health
    assert "isolated" in health
    assert health["agent_dir"].endswith("pi/agent")
    await adapter.stop()
