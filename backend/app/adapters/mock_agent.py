"""Deterministic mock coding agent.

Purpose: let the entire product path (task creation → live events → progress →
completion → cancellation → steering) be built, demonstrated and tested before
the real Pi RPC integration exists. It performs **no** file modification.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any

from ..domain import EventType
from .base import AgentEvent, AgentResult, EventCallback

#: Directories never treated as interesting project content.
_IGNORED = {
    ".git",
    "node_modules",
    "venv",
    ".venv",
    "__pycache__",
    "dist",
    "build",
    ".next",
    ".idea",
    ".vscode",
    ".mypy_cache",
    ".pytest_cache",
}


def _sample_files(cwd: str, *, limit: int = 4) -> list[str]:
    """Return a few representative relative paths from the project tree."""
    root = Path(cwd)
    found: list[str] = []
    if not root.is_dir():
        return found
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in _IGNORED)
        for filename in sorted(filenames):
            if filename.startswith("."):
                continue
            rel = os.path.relpath(os.path.join(dirpath, filename), root)
            found.append(rel)
            if len(found) >= limit:
                return found
    return found


class MockCodingAgentAdapter:
    """Simulates a coding run with believable, ordered events."""

    name = "mock"

    def __init__(self, *, step_delay: float = 0.35) -> None:
        self._step_delay = step_delay
        self._cancels: dict[str, asyncio.Event] = {}
        self._pending_steers: dict[str, list[str]] = {}

    # -- lifecycle ------------------------------------------------------- #
    async def start(self) -> None:  # noqa: D102 - trivial
        return None

    async def stop(self) -> None:  # noqa: D102 - trivial
        for event in self._cancels.values():
            event.set()
        self._cancels.clear()

    async def health(self) -> dict[str, Any]:  # noqa: D102
        return {"backend": self.name, "available": True}

    # -- control --------------------------------------------------------- #
    async def steer(self, *, task_id: str, instruction: str) -> None:  # noqa: D102
        self._pending_steers.setdefault(task_id, []).append(instruction)

    async def cancel(self, *, task_id: str) -> None:  # noqa: D102
        # Create-and-set if the run has not started yet, so a cancel that
        # arrives before the first step is not lost.
        event = self._cancels.get(task_id)
        if event is None:
            event = asyncio.Event()
            self._cancels[task_id] = event
        event.set()

    # -- run ------------------------------------------------------------- #
    async def run(
        self,
        *,
        task_id: str,
        prompt: str,
        cwd: str,
        on_event: EventCallback,
    ) -> AgentResult:
        cancel = self._cancels.setdefault(task_id, asyncio.Event())
        self._pending_steers.setdefault(task_id, [])
        files = _sample_files(cwd)
        primary = files[0] if files else "src/main.py"
        test_file = next((f for f in files if "test" in f.lower()), "tests/test_main.py")

        await on_event(
            AgentEvent(
                EventType.RUN_STARTED.value,
                f"Working on: {prompt.strip()[:160]}",
                {"cwd": cwd},
            )
        )

        steps: list[AgentEvent] = [
            AgentEvent(
                EventType.TOOL_STARTED.value,
                f"Inspecting project structure ({len(files)} sample file(s))",
                {"tool": "list_files"},
            ),
            AgentEvent(
                EventType.TOOL_FINISHED.value,
                f"Read {primary}",
                {"tool": "read_file", "path": primary},
            ),
            AgentEvent(
                EventType.PROGRESS_SUMMARY.value,
                f"Located the relevant module ({primary}) and its tests.",
                {},
            ),
            AgentEvent(
                EventType.FILE_CHANGED.value,
                f"Modified {primary}",
                {"path": primary, "change_type": "modified"},
            ),
            AgentEvent(
                EventType.TOOL_STARTED.value,
                f"Running tests ({test_file})",
                {"tool": "run_tests", "path": test_file},
            ),
            AgentEvent(
                EventType.TEST_RESULT.value,
                "Tests passed (3 passed, 0 failed)",
                {"passed": 3, "failed": 0, "path": test_file},
            ),
            AgentEvent(
                EventType.PROGRESS_SUMMARY.value,
                "The implementation is in place and the tests pass.",
                {},
            ),
        ]

        for step in steps:
            if cancel.is_set():
                await on_event(
                    AgentEvent(EventType.ERROR.value, "Run cancelled by user", {})
                )
                return AgentResult(ok=False, summary="Task cancelled.", cancelled=True)
            await self._sleep()
            await on_event(step)

            # Apply any steering instructions received since the last step.
            for instruction in self._drain_steers(task_id):
                await on_event(
                    AgentEvent(
                        EventType.PROGRESS_SUMMARY.value,
                        f"Applied follow-up instruction: {instruction.strip()[:160]}",
                        {"steered": True},
                    )
                )

        if cancel.is_set():
            return AgentResult(ok=False, summary="Task cancelled.", cancelled=True)

        await on_event(
            AgentEvent(
                EventType.RUN_FINISHED.value,
                "Task completed successfully",
                {"files_changed": 1, "tests_passed": 3},
            )
        )
        return AgentResult(
            ok=True,
            summary=f"Completed: {prompt.strip()[:120]}. 1 file changed, tests passed.",
        )

    # -- helpers --------------------------------------------------------- #
    def _drain_steers(self, task_id: str) -> list[str]:
        pending = self._pending_steers.get(task_id, [])
        self._pending_steers[task_id] = []
        return pending

    async def _sleep(self) -> None:
        if self._step_delay > 0:
            await asyncio.sleep(self._step_delay)
