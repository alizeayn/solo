"""Pi session management: one long-lived RPC process per project.

Why one process per project rather than per task:

* Pi keeps conversation context in the process, so a follow-up instruction
  ("now add tests") continues the same conversation instead of starting over.
* Steering is only meaningful against an in-flight run in the same process.
* Starting a process resolves provider auth and the model catalog, which is too
  slow to repeat for every instruction.

Sessions are keyed by the resolved project directory, which is unique per
project because external projects are de-duplicated by path and managed projects
live in distinct directories.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import dataclass, field
from typing import Any

from ..domain import EventType
from .base import AgentEvent, AgentResult, EventCallback
from .pi_events import PiEventTranslator
from .pi_rpc import (
    DEFAULT_CALL_TIMEOUT,
    PROMPT_CALL_TIMEOUT,
    PiProcessDiedError,
    PiRpcClient,
    PiRpcError,
    PiTimeoutError,
    PiUnavailableError,
)

logger = logging.getLogger(__name__)

#: How long a single coding task may run before Solo gives up on it.
DEFAULT_RUN_TIMEOUT = 30 * 60.0
#: How long to wait for Pi to become responsive after launch.
STARTUP_TIMEOUT = 45.0
#: Grace period for trailing records after `agent_settled`.
TRAILING_FLUSH = 0.35

#: Thinking levels accepted by `set_thinking_level`.
THINKING_LEVELS = ("off", "minimal", "low", "medium", "high", "xhigh", "max")


@dataclass(frozen=True)
class PiLaunchConfig:
    """Everything Solo controls about how Pi is started."""

    provider: str | None = None
    model: str | None = None
    thinking_level: str | None = None
    #: False → `--no-approve` (ignore project-local Pi resources).
    approve_project: bool = False
    #: Solo disables extensions/skills/templates/MCP by default: it assembles its
    #: own bounded context and must not hit unanswerable extension UI requests.
    minimal_harness: bool = True
    #: Ephemeral Pi session. Solo's `.solo/` store is the durable record.
    ephemeral_session: bool = True
    extra_args: tuple[str, ...] = ()

    def signature(self) -> tuple:
        return (
            self.provider,
            self.model,
            self.thinking_level,
            self.approve_project,
            self.minimal_harness,
            self.ephemeral_session,
            self.extra_args,
        )


def build_pi_argv(exec_prefix: list[str], config: PiLaunchConfig) -> list[str]:
    """Build the `pi` command line for *config*.

    ``exec_prefix`` comes from Solo's isolated runtime: an absolute Node binary
    followed by the CLI script, or an explicitly configured executable. A bare
    ``pi`` is never used.
    """
    argv = [*exec_prefix, "--mode", "rpc"]
    if config.ephemeral_session:
        argv.append("--no-session")
    argv.append("--approve" if config.approve_project else "--no-approve")
    if config.minimal_harness:
        argv += ["--no-extensions", "--no-skills", "--no-prompt-templates", "--no-mcp"]
    if config.provider:
        argv += ["--provider", config.provider]
    if config.model:
        argv += ["--model", config.model]
    if config.thinking_level and config.thinking_level in THINKING_LEVELS:
        argv += ["--thinking", config.thinking_level]
    argv += list(config.extra_args)
    return argv


@dataclass
class PiRunState:
    """In-flight run bookkeeping for one session."""

    task_id: str
    translator: PiEventTranslator
    settled: asyncio.Event = field(default_factory=asyncio.Event)
    queue: asyncio.Queue = field(default_factory=asyncio.Queue)
    consumer: asyncio.Task | None = None


class PiSession:
    """A single long-lived Pi process bound to one project directory."""

    def __init__(
        self,
        *,
        cwd: str,
        config: PiLaunchConfig,
        argv_prefix: list[str],
        env: dict[str, str] | None = None,
        run_timeout: float = DEFAULT_RUN_TIMEOUT,
    ) -> None:
        self.cwd = cwd
        self.config = config
        self._argv_prefix = list(argv_prefix)
        self._env = dict(env or {})
        self._run_timeout = run_timeout
        self._client: PiRpcClient | None = None
        self._lock = asyncio.Lock()
        self._run: PiRunState | None = None
        self._applied_signature: tuple | None = None
        self._applied_argv: list[str] | None = None

    # ------------------------------------------------------------------ #
    # Introspection
    # ------------------------------------------------------------------ #
    @property
    def argv_prefix(self) -> list[str]:
        return list(self._argv_prefix)

    @property
    def launched_argv(self) -> list[str]:
        return list(self._applied_argv or [])

    def update_runtime(self, argv_prefix: list[str], env: dict[str, str]) -> bool:
        """Adopt a new runtime. Returns True when it changed.

        Called before every run, so reinstalling or reconfiguring Solo's Pi
        installation takes effect without restarting the application.
        """
        changed = list(argv_prefix) != self._argv_prefix or dict(env) != self._env
        self._argv_prefix = list(argv_prefix)
        self._env = dict(env)
        return changed

    @property
    def running(self) -> bool:
        return self._client is not None and self._client.alive

    @property
    def pid(self) -> int | None:
        return self._client.pid if self._client is not None else None

    @property
    def busy(self) -> bool:
        return self._run is not None

    def describe(self) -> dict[str, Any]:
        return {
            "cwd": self.cwd,
            "running": self.running,
            "busy": self.busy,
            "pid": self.pid,
            "provider": self.config.provider,
            "model": self.config.model,
            "uptime": round(self._client.uptime, 1) if self._client else 0.0,
            "executable": self._argv_prefix[-1] if self._argv_prefix else None,
            "isolated": bool(self._argv_prefix),
            "last_stderr": self._client.stderr_tail(400) if self._client else "",
        }

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #
    async def ensure_started(self) -> None:
        """Start the process if needed, restarting it when anything changed."""
        signature = (self.config.signature(), tuple(self._argv_prefix))
        if self._client is not None and self._client.alive:
            if self._applied_signature == signature:
                return
            logger.info("Pi configuration changed; restarting session in %s", self.cwd)
            await self.stop()

        if not self._argv_prefix:
            raise PiUnavailableError(
                "Solo's Pi Agent runtime is not available. Install it from Settings "
                "or run './solo.sh install'."
            )

        argv = build_pi_argv(self._argv_prefix, self.config)
        client = PiRpcClient(
            argv,
            cwd=self.cwd,
            env=self._env,
            on_event=self._on_record,
            label=f"pi[{self.cwd}]",
        )
        await client.start()  # raises PiUnavailableError when unusable

        try:
            state = await client.call({"type": "get_state"}, timeout=STARTUP_TIMEOUT)
        except PiRpcError as exc:
            await client.close(grace=1.0)
            raise PiUnavailableError(f"Pi did not become ready: {exc}") from exc

        self._client = client
        self._applied_signature = signature
        self._applied_argv = argv
        model = (state or {}).get("model") or {}
        logger.info(
            "Pi session ready in %s (provider=%s model=%s isolated=%s)",
            self.cwd,
            model.get("provider"),
            model.get("id"),
            bool(self._env.get("PI_CODING_AGENT_DIR")),
        )

    async def stop(self) -> None:
        client, self._client = self._client, None
        self._applied_signature = None
        if client is not None:
            await client.close()

    # ------------------------------------------------------------------ #
    # Commands
    # ------------------------------------------------------------------ #
    async def state(self) -> dict[str, Any]:
        await self.ensure_started()
        assert self._client is not None
        return await self._client.call({"type": "get_state"}, timeout=DEFAULT_CALL_TIMEOUT)

    async def stats(self) -> dict[str, Any]:
        await self.ensure_started()
        assert self._client is not None
        return await self._client.call({"type": "get_session_stats"}, timeout=DEFAULT_CALL_TIMEOUT)

    async def apply_model(self, provider: str, model_id: str) -> dict[str, Any]:
        await self.ensure_started()
        assert self._client is not None
        return await self._client.call(
            {"type": "set_model", "provider": provider, "modelId": model_id},
            timeout=DEFAULT_CALL_TIMEOUT,
        )

    # ------------------------------------------------------------------ #
    # Running a task
    # ------------------------------------------------------------------ #
    async def run(
        self,
        *,
        task_id: str,
        prompt: str,
        on_event: EventCallback,
        timeout: float | None = None,
    ) -> AgentResult:
        """Run *prompt* to completion, streaming normalised events."""
        limit = timeout or self._run_timeout
        await self.ensure_started()
        client = self._client
        assert client is not None

        async with self._lock:
            if self._run is not None:
                raise PiRpcError("this project already has a Pi run in progress")

            translator = PiEventTranslator(cwd=self.cwd)
            state = PiRunState(task_id=task_id, translator=translator)
            self._run = state
            state.consumer = asyncio.create_task(
                self._consume(state, on_event), name=f"pi-events-{task_id[:8]}"
            )

            timed_out = False
            died = False
            try:
                await client.call(
                    {"type": "prompt", "message": prompt},
                    timeout=PROMPT_CALL_TIMEOUT,
                )
                # A run ends when Pi settles, or when the process dies — a dead
                # Pi must fail fast rather than occupy the run timeout.
                settled_wait = asyncio.create_task(state.settled.wait())
                closed_wait = asyncio.create_task(client.wait_until_closed())
                try:
                    done, _pending = await asyncio.wait(
                        {settled_wait, closed_wait},
                        timeout=limit,
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                finally:
                    for waiter in (settled_wait, closed_wait):
                        if not waiter.done():
                            waiter.cancel()

                if state.settled.is_set():
                    pass
                elif closed_wait in done:
                    died = True
                else:
                    timed_out = True
                    await self._abort_quietly()
            except PiProcessDiedError as exc:
                died = True
                translator.state.errors.append(str(exc))
            except PiRpcError as exc:
                translator.state.errors.append(str(exc))
            finally:
                await self._finish_run(state)
                self._run = None

            if died and not translator.state.errors:
                translator.state.errors.append(client.death_message())
            if timed_out and not translator.state.errors:
                translator.state.errors.append(
                    f"Pi did not finish within {int(limit)}s and was stopped"
                )
            result = translator.build_result()
            logger.info(
                "Pi run finished task=%s ok=%s cancelled=%s files=%d",
                task_id,
                result.ok,
                result.cancelled,
                len(translator.state.files_changed),
            )
            return result

    async def steer(self, instruction: str) -> None:
        """Deliver a follow-up instruction to the in-flight run."""
        client = self._client
        if client is None or not client.alive:
            raise PiProcessDiedError("no active Pi process to steer")
        await client.call(
            {
                "type": "prompt",
                "message": instruction,
                "streamingBehavior": "steer",
            },
            timeout=PROMPT_CALL_TIMEOUT,
        )

    async def cancel(self) -> None:
        """Request an abort. Completion is confirmed by `agent_settled`."""
        client = self._client
        if client is None or not client.alive:
            return
        run = self._run
        # `abort` waits for the session to become idle before responding, so it
        # can legitimately outlive a short timeout when a tool is mid-flight.
        with contextlib.suppress(PiRpcError):
            await client.call({"type": "abort"}, timeout=60.0)
        if run is not None:
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(run.settled.wait(), timeout=20.0)

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #
    def _on_record(self, record: dict[str, Any]) -> None:
        run = self._run
        if run is None:
            return
        run.queue.put_nowait(record)

    async def _consume(self, state: PiRunState, on_event: EventCallback) -> None:
        try:
            while True:
                record = await state.queue.get()
                if record is None:
                    break
                for event in state.translator.handle(record):
                    try:
                        await on_event(event)
                    except Exception:  # noqa: BLE001 - a UI/persist failure must not stop translation
                        logger.exception("Pi event callback failed")
                if record.get("type") == "agent_settled":
                    state.settled.set()
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            logger.exception("Pi event consumer failed")

    async def _finish_run(self, state: PiRunState) -> None:
        """Let trailing records flush, then stop the consumer."""
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(state.settled.wait(), timeout=0.01)
        await asyncio.sleep(TRAILING_FLUSH)
        state.queue.put_nowait(None)
        if state.consumer is not None:
            with contextlib.suppress(asyncio.TimeoutError, asyncio.CancelledError):
                await asyncio.wait_for(state.consumer, timeout=5.0)
            if not state.consumer.done():
                state.consumer.cancel()

    async def _abort_quietly(self) -> None:
        client = self._client
        if client is None or not client.alive:
            return
        with contextlib.suppress(PiRpcError):
            await client.call({"type": "abort"}, timeout=45.0)


class PiSessionManager:
    """Owns the per-project Pi sessions and the isolated runtime they use."""

    def __init__(
        self,
        runtime: Any,
        *,
        run_timeout: float = DEFAULT_RUN_TIMEOUT,
    ) -> None:
        self._runtime = runtime
        self._run_timeout = run_timeout
        self._sessions: dict[str, PiSession] = {}
        self._lock = asyncio.Lock()

    @property
    def runtime(self) -> Any:
        return self._runtime

    @property
    def executable_available(self) -> bool:
        return self._runtime is not None and self._runtime.resolve_argv() is not None

    async def session_for(self, cwd: str, config: PiLaunchConfig) -> PiSession:
        argv_prefix = self._runtime.resolve_argv() if self._runtime else None
        env = self._runtime.env() if self._runtime else {}
        if argv_prefix is None:
            raise PiUnavailableError(
                "Solo's isolated Pi Agent runtime is not installed. Install it from "
                "Settings → Pi Agent, or run './solo.sh install'."
            )

        async with self._lock:
            session = self._sessions.get(cwd)
            if session is None:
                session = PiSession(
                    cwd=cwd,
                    config=config,
                    argv_prefix=argv_prefix,
                    env=env,
                    run_timeout=self._run_timeout,
                )
                self._sessions[cwd] = session
            else:
                session.config = config
                # A reinstall or a credential change must take effect on the next
                # run, so the runtime is re-read every time.
                session.update_runtime(argv_prefix, env)
            return session

    def peek(self, cwd: str) -> PiSession | None:
        return self._sessions.get(cwd)

    def describe(self) -> list[dict[str, Any]]:
        return [session.describe() for session in self._sessions.values()]

    async def shutdown(self) -> None:
        sessions = list(self._sessions.values())
        self._sessions.clear()
        await asyncio.gather(
            *(session.stop() for session in sessions), return_exceptions=True
        )


def no_model_event() -> AgentEvent:
    """A helpful, actionable message when Pi has no model selected."""
    return AgentEvent(
        EventType.ERROR.value,
        "Pi has no model selected. Choose a provider and model in Settings → Pi Agent.",
        {"reason": "no_model"},
    )
