"""Translate Pi RPC records into Solo's normalised event vocabulary.

This is the only module that understands Pi's record shapes. Everything
downstream (task state, event storage, the WebSocket, the UI) sees
:class:`~app.adapters.base.AgentEvent` values and never a Pi record.

Two deliberate omissions:

* **Thinking blocks are discarded.** Solo shows observable tool activity and
  user-facing summaries, never private chain-of-thought.
* **Streaming text is coalesced.** ``message_update`` deltas are buffered and
  emitted once as a single ``assistant.message`` when the message ends, so one
  assistant response never becomes hundreds of stored rows.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from ..domain import EventType
from .base import AgentEvent, AgentResult

logger = logging.getLogger(__name__)

#: Tools that create or modify files, and the argument that names the target.
_FILE_TOOLS = {
    "write": ("file_path", "path", "filePath", "filename"),
    "edit": ("file_path", "path", "filePath", "filename"),
    "multi_edit": ("file_path", "path", "filePath", "filename"),
    "create": ("file_path", "path", "filePath", "filename"),
    "apply_patch": ("file_path", "path", "filePath"),
}

#: Tools that only read, with a human-facing verb.
_READ_TOOLS = {
    "read": "Reading",
    "read_file": "Reading",
    "list": "Listing",
    "list_files": "Listing",
    "glob": "Searching files",
    "grep": "Searching",
    "search": "Searching",
}

#: Command fragments that suggest a test run rather than a generic command.
_TEST_PATTERN = re.compile(
    r"\b(pytest|py\.test|unittest|npm\s+(run\s+)?test|yarn\s+test|pnpm\s+test|"
    r"vitest|jest|mocha|go\s+test|cargo\s+test|mvn\s+test|gradle\s+test|"
    r"dotnet\s+test|rspec|phpunit|make\s+test)\b",
    re.IGNORECASE,
)

#: Recognise a pytest-style summary line, e.g. "3 passed, 1 failed in 0.4s".
_TEST_SUMMARY = re.compile(
    r"(?P<passed>\d+)\s+passed|(?P<failed>\d+)\s+failed|"
    r"(?P<error>\d+)\s+error|(?P<skipped>\d+)\s+skipped|"
    r"(?P<total>\d+)\s+tests?\b",
    re.IGNORECASE,
)

MAX_MESSAGE_CHARS = 4000
MAX_EVENT_TEXT = 500


def _truncate(text: str, limit: int = MAX_EVENT_TEXT) -> str:
    text = (text or "").strip().replace("\r\n", "\n")
    if len(text) <= limit:
        return text
    return f"{text[: limit - 1].rstrip()}…"


def _arg(args: dict[str, Any], names: tuple[str, ...]) -> str | None:
    for name in names:
        value = args.get(name)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _relative(path: str, cwd: str) -> str:
    """Present a path relative to the project root when it is inside it."""
    if not path or not cwd:
        return path
    normalised_cwd = cwd.rstrip("/")
    if path == normalised_cwd:
        return "."
    prefix = f"{normalised_cwd}/"
    return path[len(prefix):] if path.startswith(prefix) else path


def summarise_test_output(output: str) -> str | None:
    """Extract a concise pass/fail line from test output, if present."""
    for line in reversed(output.splitlines()):
        stripped = line.strip()
        if not stripped:
            continue
        if _TEST_SUMMARY.search(stripped):
            return _truncate(stripped, 200)
        if len(stripped) > 200 or "=" * 10 in stripped:
            continue
    return None


@dataclass
class TranslationState:
    """Accumulated facts about one run, used to build its result."""

    files_changed: dict[str, str] = field(default_factory=dict)
    tools_used: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    test_summaries: list[str] = field(default_factory=list)
    assistant_texts: list[str] = field(default_factory=list)
    turns: int = 0
    aborted: bool = False
    settled: bool = False
    compaction_count: int = 0

    def summary(self) -> str:
        """A short, factual description of what happened."""
        if self.aborted:
            return "Task cancelled."
        if self.errors:
            return _truncate(self.errors[-1], 300)
        if self.assistant_texts:
            return _truncate(self.assistant_texts[-1], 400)
        parts: list[str] = []
        if self.files_changed:
            parts.append(
                f"{len(self.files_changed)} file(s) changed: "
                + ", ".join(list(self.files_changed)[:5])
            )
        if self.test_summaries:
            parts.append(f"tests: {self.test_summaries[-1]}")
        if not parts and self.tools_used:
            parts.append(f"ran {len(self.tools_used)} tool call(s)")
        return ". ".join(parts) or "Pi finished without reporting any changes."


class PiEventTranslator:
    """Stateful translator for one task run."""

    def __init__(self, *, cwd: str = "") -> None:
        self._cwd = cwd
        self.state = TranslationState()
        self._text_buffer: list[str] = []
        self._tool_names: dict[str, str] = {}
        self._tool_args: dict[str, dict[str, Any]] = {}
        self._bash_tools: dict[str, str] = {}
        self._tool_descriptions: dict[str, str] = {}

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def handle(self, record: dict[str, Any]) -> list[AgentEvent]:
        """Translate one Pi record into zero or more normalised events."""
        handler = getattr(self, f"_on_{record.get('type', '')}", None)
        if handler is None:
            return self._on_unknown(record)
        try:
            return handler(record) or []
        except Exception:  # noqa: BLE001 - a bad record must not break a run
            logger.warning("could not translate Pi record type=%s", record.get("type"), exc_info=True)
            return []

    @property
    def settled(self) -> bool:
        return self.state.settled

    def build_result(self, *, ok: bool | None = None) -> AgentResult:
        """Produce the terminal :class:`AgentResult` for this run."""
        failed = bool(self.state.errors)
        succeeded = (not failed) and not self.state.aborted if ok is None else ok
        return AgentResult(
            ok=succeeded and not self.state.aborted,
            summary=self.state.summary(),
            error=self.state.errors[-1] if failed else None,
            cancelled=self.state.aborted,
        )

    # ------------------------------------------------------------------ #
    # Agent / turn
    # ------------------------------------------------------------------ #
    def _on_agent_start(self, _record: dict[str, Any]) -> list[AgentEvent]:
        return [AgentEvent(EventType.RUN_STARTED.value, "Pi started working", {})]

    def _on_turn_start(self, _record: dict[str, Any]) -> list[AgentEvent]:
        self.state.turns += 1
        return []

    def _on_turn_end(self, _record: dict[str, Any]) -> list[AgentEvent]:
        return []

    def _on_agent_end(self, record: dict[str, Any]) -> list[AgentEvent]:
        if record.get("willRetry"):
            return [
                AgentEvent(
                    EventType.PROGRESS_SUMMARY.value,
                    "Pi is retrying after a transient provider error",
                    {"retrying": True},
                )
            ]
        return []

    def _on_agent_settled(self, record: dict[str, Any]) -> list[AgentEvent]:
        self.state.settled = True
        self.state.aborted = bool(record.get("aborted"))
        self._flush_text()
        if self.state.aborted:
            return [AgentEvent(EventType.RUN_FINISHED.value, "Run aborted", {"aborted": True})]
        return [AgentEvent(EventType.RUN_FINISHED.value, "Run finished", {"aborted": False})]

    # ------------------------------------------------------------------ #
    # Messages
    # ------------------------------------------------------------------ #
    def _on_message_start(self, record: dict[str, Any]) -> list[AgentEvent]:
        message = record.get("message") or {}
        if message.get("role") == "assistant":
            self._text_buffer = []
        return []

    def _on_message_update(self, record: dict[str, Any]) -> list[AgentEvent]:
        update = record.get("assistantMessageEvent") or {}
        if update.get("type") == "text_delta":
            delta = update.get("delta")
            if isinstance(delta, str):
                self._text_buffer.append(delta)
        # thinking_delta / toolcall_* are intentionally ignored here.
        return []

    def _on_message_end(self, record: dict[str, Any]) -> list[AgentEvent]:
        message = record.get("message") or {}
        role = message.get("role")

        if role == "assistant":
            events = self._flush_text(fallback=message)
            stop_reason = message.get("stopReason")
            if stop_reason == "error":
                detail = _extract_error(message)
                self.state.errors.append(detail)
                events.append(AgentEvent(EventType.ERROR.value, detail, {"stop_reason": "error"}))
            elif stop_reason == "aborted":
                self.state.aborted = True
            return events

        if role == "toolResult":
            is_error = bool(message.get("isError"))
            tool_name = str(message.get("toolName") or "tool")
            if is_error:
                detail = self._tool_result_text(message) or f"{tool_name} failed"
                self.state.errors.append(detail)
                return [AgentEvent(EventType.ERROR.value, f"{tool_name} failed: {_truncate(detail, 300)}", {"tool": tool_name})]
            return []

        return []

    def _flush_text(self, fallback: dict[str, Any] | None = None) -> list[AgentEvent]:
        text = "".join(self._text_buffer).strip()
        self._text_buffer = []
        if not text and fallback is not None:
            text = self._content_text(fallback.get("content"))
        if not text:
            return []
        self.state.assistant_texts.append(text)
        return [
            AgentEvent(
                EventType.ASSISTANT_MESSAGE.value,
                text[:MAX_MESSAGE_CHARS],
                {"chars": len(text)},
            )
        ]

    # ------------------------------------------------------------------ #
    # Tools
    # ------------------------------------------------------------------ #
    def _on_tool_execution_start(self, record: dict[str, Any]) -> list[AgentEvent]:
        tool_call_id = str(record.get("toolCallId") or "")
        tool_name = str(record.get("toolName") or "tool")
        args = record.get("args") or {}
        if not isinstance(args, dict):
            args = {}
        self._tool_names[tool_call_id] = tool_name
        self._tool_args[tool_call_id] = args
        self.state.tools_used.append(tool_name)

        if tool_name in _FILE_TOOLS:
            path = _arg(args, _FILE_TOOLS[tool_name])
            if path:
                rel = _relative(path, self._cwd)
                self.state.files_changed[rel] = "written" if tool_name in {"write", "create"} else "modified"
                return [
                    AgentEvent(
                        EventType.FILE_CHANGED.value,
                        f"{'Created' if tool_name in {'write', 'create'} else 'Modified'} {rel}",
                        {"path": rel, "change_type": self.state.files_changed[rel], "tool": tool_name},
                    )
                ]
            return [AgentEvent(EventType.TOOL_STARTED.value, "Preparing a file change", {"tool": tool_name})]

        if tool_name == "bash":
            command = str(args.get("command") or "")
            self._bash_tools[tool_call_id] = command
            is_test = bool(_TEST_PATTERN.search(command))
            label = "Running tests" if is_test else "Running a command"
            return [
                AgentEvent(
                    EventType.TOOL_STARTED.value,
                    f"{label}: {_truncate(command, 180)}",
                    {"tool": "bash", "command": _truncate(command, 400), "is_test": is_test},
                )
            ]

        verb = _READ_TOOLS.get(tool_name)
        if verb:
            target = _arg(args, ("path", "file_path", "pattern", "query")) or ""
            message = f"{verb} {_relative(target, self._cwd)}".strip()
            return [AgentEvent(EventType.TOOL_STARTED.value, message, {"tool": tool_name})]

        description = _truncate(str(args.get("description") or tool_name), 160)
        self._tool_descriptions[tool_call_id] = description
        return [AgentEvent(EventType.TOOL_STARTED.value, f"Using {tool_name}: {description}", {"tool": tool_name})]

    def _on_tool_execution_update(self, record: dict[str, Any]) -> list[AgentEvent]:
        return []

    def _on_tool_execution_end(self, record: dict[str, Any]) -> list[AgentEvent]:
        tool_call_id = str(record.get("toolCallId") or "")
        tool_name = str(record.get("toolName") or self._tool_names.get(tool_call_id, "tool"))
        is_error = bool(record.get("isError"))
        duration = record.get("durationMs")

        if is_error:
            detail = self._result_text(record.get("result")) or f"{tool_name} failed"
            self.state.errors.append(detail)
            return [AgentEvent(EventType.ERROR.value, f"{tool_name} failed: {_truncate(detail, 300)}", {"tool": tool_name})]

        if tool_name == "bash":
            command = self._bash_tools.pop(tool_call_id, "")
            output = self._result_text(record.get("result"))
            is_test = bool(_TEST_PATTERN.search(command))
            meta: dict[str, Any] = {"tool": "bash", "command": _truncate(command, 400)}
            if duration is not None:
                meta["duration_ms"] = duration
            if is_test:
                summary = summarise_test_output(output) or "test command finished"
                self.state.test_summaries.append(summary)
                return [
                    AgentEvent(EventType.TEST_RESULT.value, f"Tests finished: {summary}", meta)
                ]
            return [
                AgentEvent(
                    EventType.TOOL_FINISHED.value,
                    f"Command finished: {_truncate(command, 120)}",
                    meta,
                )
            ]

        if tool_name in _FILE_TOOLS:
            return []

        description = self._tool_descriptions.pop(tool_call_id, tool_name)
        meta = {"tool": tool_name}
        if duration is not None:
            meta["duration_ms"] = duration
        return [AgentEvent(EventType.TOOL_FINISHED.value, f"Finished {description}", meta)]

    # ------------------------------------------------------------------ #
    # Queue, compaction, retry, extensions
    # ------------------------------------------------------------------ #
    def _on_queue_update(self, record: dict[str, Any]) -> list[AgentEvent]:
        steering = record.get("steering") or []
        follow_up = record.get("followUp") or []
        total = len(steering) + len(follow_up)
        if total == 0:
            return []
        return [
            AgentEvent(
                EventType.PROGRESS_SUMMARY.value,
                f"Pi queued {total} pending instruction(s)",
                {"steering": len(steering), "follow_up": len(follow_up)},
            )
        ]

    def _on_compaction_start(self, record: dict[str, Any]) -> list[AgentEvent]:
        reason = record.get("reason") or "threshold"
        return [
            AgentEvent(
                EventType.PROGRESS_SUMMARY.value,
                f"Condensing conversation context ({reason})",
                {"compaction": reason},
            )
        ]

    def _on_compaction_end(self, record: dict[str, Any]) -> list[AgentEvent]:
        self.state.compaction_count += 1
        if record.get("errorMessage"):
            return [
                AgentEvent(
                    EventType.ERROR.value,
                    f"Context compaction failed: {_truncate(str(record['errorMessage']), 200)}",
                    {},
                )
            ]
        return [
            AgentEvent(EventType.PROGRESS_SUMMARY.value, "Conversation context condensed", {})
        ]

    def _on_auto_retry_start(self, record: dict[str, Any]) -> list[AgentEvent]:
        attempt = record.get("attempt")
        maximum = record.get("maxAttempts")
        delay = record.get("delayMs")
        message = f"Provider error; retrying ({attempt}/{maximum})"
        if delay:
            message += f" in {round(float(delay) / 1000, 1)}s"
        return [
            AgentEvent(
                EventType.PROGRESS_SUMMARY.value,
                message,
                {"attempt": attempt, "max_attempts": maximum, "retrying": True},
            )
        ]

    def _on_auto_retry_end(self, record: dict[str, Any]) -> list[AgentEvent]:
        if record.get("success"):
            return [
                AgentEvent(
                    EventType.PROGRESS_SUMMARY.value,
                    f"Provider recovered on attempt {record.get('attempt')}",
                    {"recovered": True},
                )
            ]
        final = record.get("finalError") or "provider unavailable"
        self.state.errors.append(str(final))
        return [
            AgentEvent(EventType.ERROR.value, f"Provider error after retries: {_truncate(str(final), 240)}", {})
        ]

    def _on_extension_error(self, record: dict[str, Any]) -> list[AgentEvent]:
        return [
            AgentEvent(
                EventType.ERROR.value,
                f"Pi extension error in {record.get('event')}: {_truncate(str(record.get('error')), 200)}",
                {},
            )
        ]

    def _on_extension_ui_request(self, record: dict[str, Any]) -> list[AgentEvent]:
        # Solo launches Pi with --no-extensions, so this should not occur. If an
        # extension is enabled later, surface it as a visible notice rather than
        # silently dropping it.
        return [
            AgentEvent(
                EventType.PROGRESS_SUMMARY.value,
                "A Pi extension requested interactive input, which Solo cannot display",
                {"extension_ui": True, "id": record.get("id")},
            )
        ]

    def _on_bash_execution_update(self, _record: dict[str, Any]) -> list[AgentEvent]:
        return []

    def _on_session_info_changed(self, _record: dict[str, Any]) -> list[AgentEvent]:
        return []

    def _on_thinking_level_changed(self, _record: dict[str, Any]) -> list[AgentEvent]:
        return []

    def _on_entry_appended(self, _record: dict[str, Any]) -> list[AgentEvent]:
        return []

    def _on_unknown(self, record: dict[str, Any]) -> list[AgentEvent]:
        logger.debug("ignoring unknown Pi record type=%s", record.get("type"))
        return []

    # ------------------------------------------------------------------ #
    # Content helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _content_text(content: Any) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = [
                block.get("text", "")
                for block in content
                if isinstance(block, dict) and block.get("type") == "text"
            ]
            return "".join(parts)
        return ""

    def _result_text(self, result: Any) -> str:
        if isinstance(result, dict):
            return self._content_text(result.get("content")) or str(result.get("error") or "")
        return self._content_text(result)

    def _tool_result_text(self, message: dict[str, Any]) -> str:
        return self._content_text(message.get("content"))


def provider_error_text(message: dict[str, Any]) -> str:
    """Build a human-readable provider error from an assistant message.

    Provider payloads are often JSON; the ``message`` field is preferred over
    the raw blob so the UI shows something actionable.
    """
    raw = message.get("errorMessage") or ""
    text = str(raw).strip()
    if not text:
        for block in message.get("content") or []:
            if isinstance(block, dict) and block.get("type") == "text":
                text = str(block.get("text") or "").strip()
                break
    if not text:
        text = "Pi reported a provider error"
    if text.startswith("{"):
        try:
            payload = json.loads(text)
        except ValueError:
            return _truncate(text, 400)
        for key in ("message", "error", "detail"):
            value = payload.get(key)
            if isinstance(value, str) and value:
                code = payload.get("code")
                return _truncate(f"{value}" + (f" (code {code})" if code else ""), 400)
        return _truncate(text, 400)
    return _truncate(text, 400)


#: Backwards-compatible private alias used inside this module.
_extract_error = provider_error_text
