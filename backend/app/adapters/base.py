"""Adapter contracts.

Everything the orchestrator needs from a coding agent is expressed here. The
orchestrator never imports a provider SDK or parses provider protocol records
directly — that is the adapter's job.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(slots=True)
class AgentEvent:
    """A normalised event emitted by a coding agent while a task runs."""

    type: str
    message: str
    data: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class AgentResult:
    """Terminal outcome of an agent run."""

    ok: bool
    summary: str
    error: str | None = None
    cancelled: bool = False


#: Coroutine invoked for every normalised event. Persisting and broadcasting is
#: the caller's (orchestrator's) responsibility, not the adapter's.
EventCallback = Callable[[AgentEvent], Awaitable[None]]


@runtime_checkable
class CodingAgentAdapter(Protocol):
    """Minimal contract implemented by every coding-agent backend."""

    name: str

    async def start(self) -> None:
        """Perform one-time setup (spawn a long-lived process, etc.)."""

    async def run(
        self,
        *,
        task_id: str,
        prompt: str,
        cwd: str,
        on_event: EventCallback,
    ) -> AgentResult:
        """Run *prompt* to completion in *cwd*, streaming normalised events."""

    async def steer(self, *, task_id: str, instruction: str) -> None:
        """Send a follow-up instruction to an in-flight run."""

    async def cancel(self, *, task_id: str) -> None:
        """Request cancellation of an in-flight run."""

    async def stop(self) -> None:
        """Release resources on application shutdown."""

    async def health(self) -> dict[str, Any]:
        """Return a small status dict for the health endpoint."""
