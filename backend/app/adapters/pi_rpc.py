"""Pi RPC transport.

A small, dependency-free client for `pi --mode rpc`: process launch, JSONL
framing, request/response correlation, event delivery, and orderly shutdown.

Design notes (see `Pi Agent Docs/20-solo-integration.md` for the evidence):

* **Framing is LF-only.** The stream is read with ``StreamReader.readline()``,
  which splits on ``0x0A`` and nothing else. A generic line reader that also
  treats Unicode separators (``U+2028``/``U+2029``) as boundaries would corrupt
  valid JSON, so one is deliberately not used.
* **stdout is protocol, stderr is diagnostics.** They are read by separate
  tasks; stderr is kept as a bounded tail for error reporting and never parsed.
* **Commands are correlated by id**, never by arrival order: command handling is
  asynchronous, so responses can interleave with events.
* **A successful response means "accepted", not "finished".** Callers must wait
  for ``agent_settled`` before treating a run as over.
* **A process that exits cleanly has not necessarily succeeded.** Provider
  failures arrive as ``message_end`` records with an error stop reason.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import shutil
import time
from collections import deque
from collections.abc import Callable, Iterable
from typing import Any

logger = logging.getLogger(__name__)

#: A single JSONL record can carry a large tool result; the default 64 KiB
#: StreamReader limit is far too small.
STREAM_LIMIT = 32 * 1024 * 1024
#: Retained stderr lines, used only for error messages.
STDERR_TAIL_LINES = 200

#: Default per-command deadlines.
DEFAULT_CALL_TIMEOUT = 120.0
PROMPT_CALL_TIMEOUT = 60.0


class PiRpcError(RuntimeError):
    """A Pi command failed, or the protocol misbehaved."""


class PiUnavailableError(PiRpcError):
    """The ``pi`` executable could not be started."""


class PiProcessDiedError(PiRpcError):
    """The Pi process exited or closed its pipes."""


class PiTimeoutError(PiRpcError):
    """Pi did not answer a command in time."""


RawRecordHandler = Callable[[dict[str, Any]], Any]
RecordPredicate = Callable[[dict[str, Any]], bool]


class PiRpcClient:
    """One `pi --mode rpc` child process."""

    def __init__(
        self,
        argv: Iterable[str],
        *,
        cwd: str,
        env: dict[str, str] | None = None,
        on_event: RawRecordHandler | None = None,
        on_stderr: Callable[[str], None] | None = None,
        label: str = "pi",
        stream_limit: int = STREAM_LIMIT,
    ) -> None:
        self._argv = list(argv)
        self._cwd = cwd
        self._env = dict(env or {})
        self._on_event = on_event
        self._on_stderr = on_stderr
        self._label = label
        self._stream_limit = stream_limit

        self._proc: asyncio.subprocess.Process | None = None
        self._stdout_task: asyncio.Task[None] | None = None
        self._stderr_task: asyncio.Task[None] | None = None
        self._pending: dict[str, asyncio.Future[dict[str, Any]]] = {}
        self._waiters: list[tuple[RecordPredicate, asyncio.Future[dict[str, Any]]]] = []
        self._stderr_tail: deque[str] = deque(maxlen=STDERR_TAIL_LINES)
        self._counter = 0
        self._closing = False
        self._started_at: float | None = None
        self._exit_code: int | None = None
        #: Set once the process is gone, so callers can stop waiting on events
        #: that will never arrive (a crashed Pi must not look like a hang).
        self._closed_event = asyncio.Event()

    # ------------------------------------------------------------------ #
    # Introspection
    # ------------------------------------------------------------------ #
    @property
    def argv(self) -> list[str]:
        return list(self._argv)

    @property
    def pid(self) -> int | None:
        return self._proc.pid if self._proc is not None else None

    @property
    def alive(self) -> bool:
        if self._proc is None or self._closing:
            return False
        return self._proc.returncode is None

    @property
    def exit_code(self) -> int | None:
        return self._exit_code

    @property
    def uptime(self) -> float:
        return 0.0 if self._started_at is None else time.monotonic() - self._started_at

    def death_message(self) -> str:
        """A description of why the process ended, for error reporting."""
        return self._death_message()

    async def wait_until_closed(self) -> None:
        """Resolve when the process has ended and its pipes are drained."""
        await self._closed_event.wait()

    def stderr_tail(self, max_chars: int = 2000) -> str:
        """Recent diagnostics, for error messages. Never contains stdout."""
        text = "\n".join(self._stderr_tail)
        return text[-max_chars:]

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #
    async def start(self) -> None:
        if self.alive:
            return
        executable = shutil.which(self._argv[0])
        if executable is None:
            raise PiUnavailableError(
                f"the '{self._argv[0]}' executable was not found on PATH"
            )
        env = {**os.environ, **self._env}
        try:
            self._proc = await asyncio.create_subprocess_exec(
                executable,
                *self._argv[1:],
                cwd=self._cwd,
                env=env,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                limit=self._stream_limit,
            )
        except OSError as exc:
            raise PiUnavailableError(
                f"could not start Pi in {self._cwd}: {exc.strerror or exc}"
            ) from exc

        self._closing = False
        self._exit_code = None
        self._started_at = time.monotonic()
        self._closed_event = asyncio.Event()
        self._stdout_task = asyncio.create_task(
            self._read_stdout(), name=f"{self._label}-stdout"
        )
        self._stderr_task = asyncio.create_task(
            self._read_stderr(), name=f"{self._label}-stderr"
        )
        logger.info("started %s (pid=%s) in %s", self._label, self.pid, self._cwd)

    async def close(self, *, grace: float = 8.0) -> None:
        """Orderly shutdown: close stdin, wait, then escalate."""
        if self._closing:
            return
        self._closing = True
        proc = self._proc
        if proc is None:
            return
        try:
            if proc.stdin is not None and not proc.stdin.is_closing():
                # Pi disposes its runtime when stdin closes.
                proc.stdin.close()
            try:
                await asyncio.wait_for(proc.wait(), timeout=grace)
            except asyncio.TimeoutError:
                logger.warning("%s did not exit in %.0fs; terminating", self._label, grace)
                with contextlib.suppress(ProcessLookupError):
                    proc.terminate()
                try:
                    await asyncio.wait_for(proc.wait(), timeout=3.0)
                except asyncio.TimeoutError:
                    with contextlib.suppress(ProcessLookupError):
                        proc.kill()
                    with contextlib.suppress(asyncio.TimeoutError):
                        await asyncio.wait_for(proc.wait(), timeout=3.0)
        finally:
            self._exit_code = proc.returncode
            for task in (self._stdout_task, self._stderr_task):
                if task is not None and not task.done():
                    task.cancel()
            self._fail_pending(PiProcessDiedError("Pi client closed"))
            self._closed_event.set()
            logger.info("%s stopped (exit=%s)", self._label, self._exit_code)

    # ------------------------------------------------------------------ #
    # Reading
    # ------------------------------------------------------------------ #
    async def _read_stdout(self) -> None:
        proc = self._proc
        if proc is None or proc.stdout is None:
            return
        stdout = proc.stdout
        try:
            while True:
                try:
                    line = await stdout.readline()
                except (asyncio.LimitOverrunError, ValueError):
                    logger.warning("%s: oversized protocol record skipped", self._label)
                    continue
                if not line:
                    break
                text = line.decode("utf-8", "replace").rstrip("\r\n")
                if not text.strip():
                    continue
                try:
                    record = json.loads(text)
                except ValueError:
                    logger.warning(
                        "%s: malformed JSON record skipped (%d bytes)", self._label, len(text)
                    )
                    continue
                if isinstance(record, dict):
                    self._dispatch(record)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - the reader must never kill the app
            logger.exception("%s: stdout reader failed", self._label)
        finally:
            self._fail_pending(PiProcessDiedError(self._death_message()))

    async def _read_stderr(self) -> None:
        proc = self._proc
        if proc is None or proc.stderr is None:
            return
        stderr = proc.stderr
        try:
            while True:
                line = await stderr.readline()
                if not line:
                    break
                text = line.decode("utf-8", "replace").rstrip()
                if not text:
                    continue
                self._stderr_tail.append(text)
                if self._on_stderr is not None:
                    with contextlib.suppress(Exception):
                        self._on_stderr(text)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            logger.debug("%s: stderr reader stopped", self._label, exc_info=True)

    def _death_message(self) -> str:
        code = self._exit_code
        if code is None and self._proc is not None:
            code = self._proc.returncode
        tail = self.stderr_tail(max_chars=600)
        message = f"Pi exited unexpectedly (code={code})" if code is not None else "Pi stream closed"
        return f"{message}: {tail}" if tail else message

    def _dispatch(self, record: dict[str, Any]) -> None:
        if record.get("type") == "response":
            request_id = record.get("id")
            if request_id:
                future = self._pending.pop(request_id, None)
                if future is not None and not future.done():
                    future.set_result(record)
                    return
                # A response for a request we already timed out on.
                return
            if record.get("command") == "parse":
                logger.warning("%s: %s", self._label, record.get("error"))
            return

        for predicate, future in list(self._waiters):
            if future.done():
                self._waiters.remove((predicate, future))
                continue
            try:
                if predicate(record):
                    self._waiters.remove((predicate, future))
                    future.set_result(record)
            except Exception:  # noqa: BLE001 - a bad predicate must not break the stream
                logger.debug("record predicate raised", exc_info=True)

        if self._on_event is not None:
            try:
                result = self._on_event(record)
                if asyncio.iscoroutine(result):
                    asyncio.create_task(result)  # noqa: RUF006 - fire and forget
            except Exception:  # noqa: BLE001
                logger.exception("%s: event handler failed", self._label)

    # ------------------------------------------------------------------ #
    # Writing
    # ------------------------------------------------------------------ #
    async def _write(self, payload: dict[str, Any]) -> None:
        proc = self._proc
        if proc is None or proc.stdin is None or proc.stdin.is_closing():
            raise PiProcessDiedError("Pi stdin is not available")
        data = (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8")
        try:
            proc.stdin.write(data)
            await proc.stdin.drain()  # honour backpressure
        except (BrokenPipeError, ConnectionResetError) as exc:
            raise PiProcessDiedError("Pi closed its stdin") from exc

    def next_id(self) -> str:
        self._counter += 1
        return f"solo-{self._counter}"

    async def call(
        self,
        command: dict[str, Any],
        *,
        timeout: float = DEFAULT_CALL_TIMEOUT,
        accept_failure: bool = False,
    ) -> dict[str, Any]:
        """Send *command* and return its correlated ``data`` payload.

        Raises :class:`PiRpcError` when Pi reports ``success: false``. With
        *accept_failure* the full response record is returned instead, so the
        caller can inspect ``success`` and ``error`` itself.
        """
        if not self.alive:
            raise PiProcessDiedError(self._death_message())

        request_id = command.get("id") or self.next_id()
        payload = {**command, "id": request_id}
        future: asyncio.Future[dict[str, Any]] = (
            asyncio.get_running_loop().create_future()
        )
        self._pending[request_id] = future
        try:
            await self._write(payload)
            try:
                record = await asyncio.wait_for(future, timeout=timeout)
            except asyncio.TimeoutError as exc:
                raise PiTimeoutError(
                    f"Pi did not answer '{payload.get('type')}' within {timeout:g}s"
                ) from exc
        finally:
            self._pending.pop(request_id, None)

        if not record.get("success", False):
            if accept_failure:
                return record
            raise PiRpcError(
                record.get("error") or f"{payload.get('type')} failed"
            )
        # Success: unwrap to the command's data payload. ``accept_failure``
        # callers receive the whole record so they can inspect `error`.
        return record.get("data") or {}

    async def notify(self, command: dict[str, Any]) -> str:
        """Fire-and-forget send. Returns the request id used."""
        request_id = command.get("id") or self.next_id()
        await self._write({**command, "id": request_id})
        return request_id

    async def wait_for(
        self,
        predicate: RecordPredicate,
        *,
        timeout: float,
        description: str = "record",
    ) -> dict[str, Any]:
        """Wait until a raw record satisfies *predicate*."""
        future: asyncio.Future[dict[str, Any]] = (
            asyncio.get_running_loop().create_future()
        )
        entry = (predicate, future)
        self._waiters.append(entry)
        try:
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError as exc:
            raise PiTimeoutError(f"timed out waiting for {description}") from exc
        finally:
            with contextlib.suppress(ValueError):
                self._waiters.remove(entry)

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def _fail_pending(self, error: Exception) -> None:
        for future in self._pending.values():
            if not future.done():
                future.set_exception(error)
        self._pending.clear()
        for _predicate, future in self._waiters:
            if not future.done():
                future.set_exception(error)
        self._waiters.clear()
        self._closed_event.set()


def is_response(record: dict[str, Any]) -> bool:
    return record.get("type") == "response"


def is_event(record: dict[str, Any]) -> bool:
    return record.get("type") != "response"


def settled_predicate(record: dict[str, Any]) -> bool:
    """True once Pi will not continue automatically."""
    return record.get("type") == "agent_settled"