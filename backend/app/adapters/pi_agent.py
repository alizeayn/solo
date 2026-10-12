"""Pi Coding Agent adapter.

Implements Solo's :class:`CodingAgentAdapter` contract on top of Pi's RPC mode,
using **Solo's own isolated Pi Agent runtime** — never the host's installation.

Everything provider- or protocol-specific lives in `pi_rpc.py`, `pi_events.py`,
`pi_session.py` and `services/pi_runtime.py`.

Verified behaviour this module depends on (see `Pi Agent Docs/20-solo-integration.md`):

* a successful ``prompt`` response means *accepted*, not *finished* — only
  ``agent_settled`` ends a run;
* provider failures arrive as ``message_end`` records with an error stop reason,
  while the child process stays healthy;
* a fresh but *authenticated* agent directory resolves models from the package's
  bundled provider catalog, so isolation costs nothing.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from ..config import Settings
from ..services.pi_runtime import PiRuntime, RuntimeStatus
from .base import AgentEvent, AgentResult, EventCallback
from .pi_rpc import PiRpcError, PiUnavailableError
from .pi_session import (
    DEFAULT_RUN_TIMEOUT,
    PiLaunchConfig,
    PiSession,
    PiSessionManager,
    no_model_event,
)

logger = logging.getLogger(__name__)

ConfigLoader = Callable[[], Awaitable[PiLaunchConfig]]


@dataclass(slots=True)
class PiRuntimeInfo:
    """Summary of Solo's own Pi runtime, for health and Settings.

    Kept as a flat dataclass because it is consumed by the health endpoint and
    the Settings UI; :meth:`RuntimeStatus.to_dict` carries the fuller picture.
    """

    available: bool
    version: str | None
    rpc_supported: bool
    detail: str
    executable: str | None = None
    agent_dir: str | None = None
    #: ``managed`` (Solo's own copy), ``external`` (an explicit override), ``none``.
    source: str = "none"
    #: True only when the runtime was actually started and answered a command.
    verified: bool = False
    node: str | None = None
    runtime_dir: str | None = None
    installed_at: str | None = None
    last_error: str | None = None

    @classmethod
    def from_status(cls, status: RuntimeStatus) -> "PiRuntimeInfo":
        return cls(
            available=status.installed,
            version=status.version,
            rpc_supported=status.installed,
            detail=status.detail,
            executable=status.executable,
            agent_dir=status.agent_dir,
            source=status.source,
            verified=status.verified,
            node=status.node,
            runtime_dir=status.runtime_dir,
            installed_at=status.installed_at,
            last_error=status.last_error,
        )


async def probe_pi_runtime(
    settings: Settings, *, verify: bool = False
) -> PiRuntimeInfo:
    """Describe Solo's isolated Pi runtime. Never raises."""
    try:
        status = await PiRuntime(settings).status(verify=verify)
    except Exception as exc:  # noqa: BLE001 - a probe must never break health
        logger.warning("Pi runtime probe failed", exc_info=True)
        return PiRuntimeInfo(
            available=False,
            version=None,
            rpc_supported=False,
            detail=f"{type(exc).__name__}: {exc}",
        )
    return PiRuntimeInfo.from_status(status)


class PiCodingAgentAdapter:
    """Runs coding tasks through Solo's own managed Pi RPC subprocess."""

    name = "pi"

    def __init__(
        self,
        settings: Settings,
        *,
        config_loader: ConfigLoader | None = None,
        runtime: PiRuntime | None = None,
        manager: PiSessionManager | None = None,
        run_timeout: float = DEFAULT_RUN_TIMEOUT,
    ) -> None:
        self._settings = settings
        self._config_loader = config_loader
        self._runtime = runtime or PiRuntime(settings)
        self._manager = manager or PiSessionManager(
            self._runtime, run_timeout=run_timeout
        )
        self._by_task: dict[str, PiSession] = {}
        self._started = False

    @property
    def runtime(self) -> PiRuntime:
        return self._runtime

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #
    async def start(self) -> None:
        self._started = True
        status = await self._runtime.status()
        if not status.installed:
            logger.warning("Pi backend selected but unavailable: %s", status.detail)
        elif status.source == "external":
            logger.warning(
                "Pi backend is using an externally configured executable (%s); "
                "Solo's own isolated runtime is not in use.",
                status.executable,
            )
        else:
            logger.info(
                "Pi backend ready: %s (agent dir %s)",
                status.version or "unknown version",
                status.agent_dir,
            )

    async def stop(self) -> None:
        self._by_task.clear()
        await self._manager.shutdown()
        self._started = False

    async def health(self) -> dict[str, Any]:
        status = await self._runtime.status()
        return {
            "backend": self.name,
            **status.to_dict(),
            "sessions": self._manager.describe(),
        }

    # ------------------------------------------------------------------ #
    # Runs
    # ------------------------------------------------------------------ #
    async def _load_config(self) -> PiLaunchConfig:
        if self._config_loader is None:
            return PiLaunchConfig()
        try:
            return await self._config_loader()
        except Exception:  # noqa: BLE001 - never block a task on config lookup
            logger.warning("could not load Pi launch configuration", exc_info=True)
            return PiLaunchConfig()

    async def run(
        self,
        *,
        task_id: str,
        prompt: str,
        cwd: str,
        on_event: EventCallback,
    ) -> AgentResult:
        config = await self._load_config()
        try:
            session = await self._manager.session_for(cwd, config)
        except PiUnavailableError as exc:
            await on_event(AgentEvent("error", str(exc), {"reason": "pi_unavailable"}))
            return AgentResult(ok=False, summary=str(exc), error=str(exc))

        self._by_task[task_id] = session
        try:
            try:
                state = await session.state()
            except PiUnavailableError as exc:
                message = str(exc)
                await on_event(AgentEvent("error", message, {"reason": "pi_unavailable"}))
                return AgentResult(ok=False, summary=message, error=message)
            except PiRpcError as exc:
                message = f"Pi could not start: {exc}"
                await on_event(AgentEvent("error", message, {"reason": "pi_start_failed"}))
                return AgentResult(ok=False, summary=message, error=message)

            model = (state or {}).get("model") or {}
            model_id = str(model.get("id") or "").strip()
            # Pi reports the literal string "unknown" when the agent directory has
            # no model selected. Treating that as a model would let the run start
            # and fail deep inside the provider, which tells the user nothing.
            # Catching it here turns a confusing "No API key found for the
            # selected model" into an instruction they can act on.
            if not model_id or model_id.lower() in {"unknown", "none", "null"}:
                event = no_model_event()
                await on_event(event)
                return AgentResult(ok=False, summary=event.message, error=event.message)

            await on_event(
                AgentEvent(
                    "progress.summary",
                    f"Pi is running {model.get('id')} from Solo's own runtime",
                    {
                        "provider": model.get("provider"),
                        "model": model.get("id"),
                        "session_pid": session.pid,
                        "agent_dir": str(self._runtime.agent_dir()),
                        "source": self._runtime.source(),
                    },
                )
            )

            return await session.run(
                task_id=task_id, prompt=prompt, on_event=on_event
            )
        finally:
            self._by_task.pop(task_id, None)

    async def steer(self, *, task_id: str, instruction: str) -> None:
        session = self._by_task.get(task_id)
        if session is None:
            logger.info("steer requested for unknown or finished task %s", task_id)
            return
        try:
            await session.steer(instruction)
        except PiRpcError as exc:
            logger.warning("steer failed for task %s: %s", task_id, exc)
            raise

    async def cancel(self, *, task_id: str) -> None:
        session = self._by_task.get(task_id)
        if session is None:
            return
        await session.cancel()

    # ------------------------------------------------------------------ #
    # Diagnostics
    # ------------------------------------------------------------------ #
    def sessions(self) -> list[dict[str, Any]]:
        return self._manager.describe()
