"""Pi Coding Agent adapter.

Implements Solo's :class:`CodingAgentAdapter` contract on top of Pi's RPC mode.
This is the only place that launches Pi; everything provider- or
protocol-specific lives in `pi_rpc.py`, `pi_events.py` and `pi_session.py`.

Verified behaviour this module depends on (see `Pi Agent Docs/20-solo-integration.md`):

* a successful ``prompt`` response means *accepted*, not *finished* — only
  ``agent_settled`` ends a run;
* provider failures arrive as ``message_end`` records with an error stop reason,
  while the child process stays healthy;
* a fresh agent directory has no model catalog, so Solo never overrides Pi's
  agent directory by default.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from ..config import Settings
from .base import AgentEvent, AgentResult, EventCallback
from .pi_session import (
    DEFAULT_RUN_TIMEOUT,
    PiLaunchConfig,
    PiSession,
    PiSessionManager,
    no_model_event,
)
from .pi_rpc import PiRpcError, PiUnavailableError

logger = logging.getLogger(__name__)

ConfigLoader = Callable[[], Awaitable[PiLaunchConfig]]


@dataclass(slots=True)
class PiRuntimeInfo:
    available: bool
    version: str | None
    rpc_supported: bool
    detail: str
    executable: str | None = None
    agent_dir: str | None = None


async def probe_pi_runtime(
    *, timeout: float = 15.0, executable: str = "pi"
) -> PiRuntimeInfo:
    """Detect the ``pi`` CLI and read its version. Never raises."""
    resolved = shutil.which(executable)
    agent_dir = os.environ.get(
        "PI_CODING_AGENT_DIR", os.path.expanduser("~/.pi/agent")
    )
    if not resolved:
        return PiRuntimeInfo(
            available=False,
            version=None,
            rpc_supported=False,
            detail=(
                f"The '{executable}' executable was not found on PATH. Install it with "
                "'npm install -g @earendil-works/pi-coding-agent', then restart Solo."
            ),
            agent_dir=agent_dir,
        )
    try:
        process = await asyncio.create_subprocess_exec(
            resolved,
            "--version",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
    except (asyncio.TimeoutError, OSError) as exc:
        return PiRuntimeInfo(
            available=False,
            version=None,
            rpc_supported=False,
            detail=f"Could not run '{executable} --version': {type(exc).__name__}.",
            executable=resolved,
            agent_dir=agent_dir,
        )

    if process.returncode != 0:
        detail = (stderr or b"").decode("utf-8", "replace").strip()[:200]
        return PiRuntimeInfo(
            available=False,
            version=None,
            rpc_supported=False,
            detail=f"'{executable} --version' exited with code {process.returncode}: {detail}",
            executable=resolved,
            agent_dir=agent_dir,
        )

    version = stdout.decode("utf-8", "replace").strip() or None
    return PiRuntimeInfo(
        available=True,
        version=version,
        rpc_supported=True,
        detail=f"Pi CLI {version} detected; RPC mode available.",
        executable=resolved,
        agent_dir=agent_dir,
    )


class PiCodingAgentAdapter:
    """Runs coding tasks through a managed Pi RPC subprocess."""

    name = "pi"

    def __init__(
        self,
        settings: Settings,
        *,
        config_loader: ConfigLoader | None = None,
        manager: PiSessionManager | None = None,
        run_timeout: float = DEFAULT_RUN_TIMEOUT,
    ) -> None:
        self._settings = settings
        self._config_loader = config_loader
        self._manager = manager or PiSessionManager(
            executable=settings.pi_executable, run_timeout=run_timeout
        )
        self._by_task: dict[str, PiSession] = {}
        self._started = False

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #
    async def start(self) -> None:
        self._started = True
        info = await probe_pi_runtime(executable=self._settings.pi_executable)
        if not info.available:
            logger.warning("Pi backend selected but unavailable: %s", info.detail)

    async def stop(self) -> None:
        self._by_task.clear()
        await self._manager.shutdown()
        self._started = False

    async def health(self) -> dict[str, Any]:
        info = await probe_pi_runtime(executable=self._settings.pi_executable)
        return {
            "backend": self.name,
            "available": info.available,
            "version": info.version,
            "detail": info.detail,
            "agent_dir": info.agent_dir,
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
            if not model.get("id"):
                event = no_model_event()
                await on_event(event)
                return AgentResult(ok=False, summary=event.message, error=event.message)

            await on_event(
                AgentEvent(
                    "progress.summary",
                    f"Pi is running {model.get('id')}",
                    {
                        "provider": model.get("provider"),
                        "model": model.get("id"),
                        "session_pid": session.pid,
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
            # The run may have settled between the request and this call; a
            # missing session is not an error worth failing the task over.
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
