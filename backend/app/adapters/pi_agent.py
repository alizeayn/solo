"""Pi Coding Agent integration.

Phase 1 only *probes* the installed Pi runtime so the Settings UI can show the
version and whether the CLI is present. The managed long-lived RPC subprocess
(JSONL over stdio, request-id correlation, steering, cancellation) is
implemented in Phase 2 against the authoritative local documentation:

    docs/rpc.md, docs/rpc-commands.md, docs/cli-integration.md

Nothing here guesses package names or protocol details.
"""

from __future__ import annotations

import asyncio
import shutil
from dataclasses import dataclass

from ..config import Settings
from .base import AgentResult, EventCallback


@dataclass(slots=True)
class PiRuntimeInfo:
    available: bool
    version: str | None
    rpc_supported: bool
    detail: str


async def probe_pi_runtime(*, timeout: float = 10.0) -> PiRuntimeInfo:
    """Detect the ``pi`` CLI and read its version.

    Never raises: a missing or failing binary is reported as ``available=False``
    so the health endpoint and Settings UI can degrade gracefully.
    """
    executable = shutil.which("pi")
    if not executable:
        return PiRuntimeInfo(
            available=False,
            version=None,
            rpc_supported=False,
            detail="The 'pi' executable was not found on PATH.",
        )
    try:
        process = await asyncio.create_subprocess_exec(
            executable,
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
            detail=f"Could not run 'pi --version': {type(exc).__name__}.",
        )

    if process.returncode != 0:
        detail = (stderr or b"").decode("utf-8", "replace").strip()[:200]
        return PiRuntimeInfo(
            available=False,
            version=None,
            rpc_supported=False,
            detail=f"'pi --version' exited with code {process.returncode}: {detail}",
        )

    version = stdout.decode("utf-8", "replace").strip() or None
    return PiRuntimeInfo(
        available=True,
        version=version,
        rpc_supported=False,  # enabled in Phase 2
        detail="Pi CLI detected. RPC session management arrives in Phase 2.",
    )


class PiCodingAgentAdapter:
    """Phase 2 placeholder implementing the adapter contract.

    It exists so the interface is fixed now; every method fails loudly rather
    than pretending to work.
    """

    name = "pi"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def _not_implemented(self) -> None:
        raise RuntimeError(
            "Pi RPC integration is scheduled for Phase 2 (see docs/rpc.md)."
        )

    async def start(self) -> None:  # pragma: no cover - Phase 2
        self._not_implemented()

    async def run(
        self,
        *,
        task_id: str,  # noqa: ARG002
        prompt: str,  # noqa: ARG002
        cwd: str,  # noqa: ARG002
        on_event: EventCallback,  # noqa: ARG002
    ) -> AgentResult:  # pragma: no cover - Phase 2
        self._not_implemented()
        raise AssertionError("unreachable")

    async def steer(self, *, task_id: str, instruction: str) -> None:  # pragma: no cover
        self._not_implemented()

    async def cancel(self, *, task_id: str) -> None:  # pragma: no cover - Phase 2
        self._not_implemented()

    async def stop(self) -> None:  # pragma: no cover - Phase 2
        return None

    async def health(self) -> dict[str, object]:  # pragma: no cover - Phase 2
        info = await probe_pi_runtime()
        return {
            "backend": self.name,
            "available": info.available,
            "version": info.version,
        }
