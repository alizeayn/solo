"""Provider adapters.

Phase 1 ships a deterministic :class:`MockCodingAgentAdapter` so the whole UI
and task pipeline can be exercised end to end. Phase 2 replaces it with the
real Pi RPC adapter; :func:`build_adapter` is the single switch-over point.
"""

from __future__ import annotations

from ..config import Settings
from .base import AgentEvent, AgentResult, CodingAgentAdapter, EventCallback
from .mock_agent import MockCodingAgentAdapter
from .pi_agent import PiRuntimeInfo, probe_pi_runtime

__all__ = [
    "AgentEvent",
    "AgentResult",
    "CodingAgentAdapter",
    "EventCallback",
    "MockCodingAgentAdapter",
    "PiRuntimeInfo",
    "build_adapter",
    "probe_pi_runtime",
]


def build_adapter(
    settings: Settings, *, backend: str | None = None
) -> CodingAgentAdapter:
    """Return the configured coding-agent adapter.

    ``backend`` may be ``"mock"`` or ``"pi"``. Phase 1 only supports ``mock``;
    requesting ``pi`` raises a clear error instead of silently degrading.
    """
    chosen = (backend or "mock").lower()
    if chosen == "mock":
        return MockCodingAgentAdapter(step_delay=settings.mock_step_delay)
    if chosen == "pi":  # pragma: no cover - enabled in Phase 2
        from .pi_agent import PiCodingAgentAdapter

        return PiCodingAgentAdapter(settings)
    raise ValueError(f"unknown coding-agent backend: {backend!r}")
