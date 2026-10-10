"""Provider adapters.

Phase 2 ships two coding-agent backends behind one contract:

* :class:`MockCodingAgentAdapter` — a deterministic simulator used by tests and
  available as a fallback when Pi is not installed.
* :class:`PiCodingAgentAdapter` — the real integration, driving `pi --mode rpc`.

:func:`build_adapter` is the single switch-over point. ``agent_backend="auto"``
selects Pi when the CLI is present and falls back to the simulator otherwise,
so a fresh install works with or without Pi.
"""

from __future__ import annotations

import shutil
from collections.abc import Awaitable, Callable

from ..config import Settings
from .base import AgentEvent, AgentResult, CodingAgentAdapter, EventCallback
from .mock_agent import MockCodingAgentAdapter
from .pi_agent import PiRuntimeInfo, probe_pi_runtime
from .pi_session import PiLaunchConfig, PiSessionManager

__all__ = [
    "AgentEvent",
    "AgentResult",
    "CodingAgentAdapter",
    "EventCallback",
    "MockCodingAgentAdapter",
    "PiLaunchConfig",
    "PiRuntimeInfo",
    "PiSessionManager",
    "build_adapter",
    "probe_pi_runtime",
    "resolve_backend",
]

PiConfigLoader = Callable[[], Awaitable[PiLaunchConfig]]


def resolve_backend(settings: Settings, backend: str | None = None) -> str:
    """Resolve a backend name, expanding ``auto``."""
    chosen = (backend or settings.agent_backend or "auto").strip().lower()
    if chosen == "auto":
        return "pi" if shutil.which(settings.pi_executable) else "mock"
    return chosen


def build_adapter(
    settings: Settings,
    *,
    backend: str | None = None,
    pi_config_loader: PiConfigLoader | None = None,
) -> CodingAgentAdapter:
    """Return the configured coding-agent adapter."""
    chosen = resolve_backend(settings, backend)

    if chosen == "mock":
        return MockCodingAgentAdapter(step_delay=settings.mock_step_delay)

    if chosen == "pi":
        from .pi_agent import PiCodingAgentAdapter

        return PiCodingAgentAdapter(
            settings,
            config_loader=pi_config_loader,
            run_timeout=float(settings.pi_run_timeout_seconds),
        )

    raise ValueError(f"unknown coding-agent backend: {backend!r}")
