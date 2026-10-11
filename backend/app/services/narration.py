"""Narration: Solo's voice-native output channel.

Solo's product direction is that the **conversation is the interface** and speech
is its primary output. This module is the foundation for that: it turns agent
activity into short, ordered, non-overlapping spoken lines, and hands them to a
transport.

Phase 4 attaches a real audio transport (ElevenLabs TTS). Everything else — which
events are worth saying, how they are worded, ordering, coalescing, rate limiting
and barge-in — is decided here and is fully testable today, because the default
transport records rather than speaks.

Rules the user asked for, expressed as code:

* **Never narrate every operation.** Only milestones are announced: progress
  summaries, errors, decisions needed and completion. Tool calls are not spoken.
* **Do not overlap.** A single worker delivers one line at a time with a minimum
  interval, so two announcements can never talk over each other.
* **Drop stale announcements.** A newer progress line replaces a queued older one
  — saying "found the module" after "the tests pass" would be nonsense.
* **Yield to the user.** :meth:`interrupt` clears progress lines and marks the
  service as listening, so a lower-priority announcement is dropped rather than
  spoken over the person speaking.
* **Always shown, optionally spoken.** Every line is published to the UI whether
  or not speech is enabled, so information is never audio-only.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import IntEnum
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger(__name__)

#: Seconds between deliveries, so speech never runs together.
DEFAULT_MIN_INTERVAL = 1.5
#: Bound on queued lines; progress is dropped rather than growing without limit.
DEFAULT_MAX_QUEUE = 32


class Priority(IntEnum):
    """Lower is more urgent. Ordering is by (priority, sequence)."""

    CRITICAL = 0  # errors, a decision is needed
    IMPORTANT = 1  # task finished, summary
    PROGRESS = 2  # milestone narration


@dataclass
class NarrationLine:
    text: str
    kind: str = "progress"
    priority: int = int(Priority.PROGRESS)
    task_id: str | None = None
    project_id: str | None = None
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    spoken_at: str | None = None
    sequence: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "text": self.text,
            "kind": self.kind,
            "priority": self.priority,
            "task_id": self.task_id,
            "project_id": self.project_id,
            "created_at": self.created_at,
            "spoken_at": self.spoken_at,
        }


@runtime_checkable
class NarrationTransport(Protocol):
    """Where narration goes. Phase 4 supplies an audio implementation."""

    name: str

    async def deliver(self, line: NarrationLine) -> None:
        """Speak (or otherwise present) one line. Must not raise for lack of audio."""

    async def stop(self) -> None:
        """Stop any in-flight speech, for barge-in."""


class RecordingTransport:
    """Default transport: keeps what *would* have been said.

    Solo does not ship audio yet, so this makes the pipeline observable and
    testable — the UI shows the lines and the tests assert on them — without
    pretending speech exists.
    """

    name = "recording"

    def __init__(self, *, keep: int = 50) -> None:
        self.lines: list[NarrationLine] = []
        self._keep = keep
        self.stops = 0

    async def deliver(self, line: NarrationLine) -> None:
        line.spoken_at = datetime.now(timezone.utc).isoformat()
        self.lines.append(line)
        del self.lines[: max(0, len(self.lines) - self._keep)]

    async def stop(self) -> None:
        self.stops += 1


class NarrationService:
    """Ordered, coalescing, non-overlapping narration."""

    def __init__(
        self,
        *,
        bus: Any | None = None,
        transport: NarrationTransport | None = None,
        min_interval: float = DEFAULT_MIN_INTERVAL,
        max_queue: int = DEFAULT_MAX_QUEUE,
        enabled: Callable[[], Awaitable[bool]] | None = None,
    ) -> None:
        self._bus = bus
        self._transport = transport or RecordingTransport()
        self._min_interval = min_interval
        self._max_queue = max_queue
        self._enabled = enabled
        self._queue: list[NarrationLine] = []
        self._sequence = 0
        self._history: list[NarrationLine] = []
        self._worker: asyncio.Task[None] | None = None
        self._wake = asyncio.Event()
        self._lock = asyncio.Lock()
        self.listening = False
        self.dropped = 0

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #
    async def start(self) -> None:
        if self._worker is None or self._worker.done():
            self._worker = asyncio.create_task(self._run(), name="narration")

    async def stop(self) -> None:
        worker, self._worker = self._worker, None
        if worker is not None and not worker.done():
            worker.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await worker
        with contextlib.suppress(Exception):
            await self._transport.stop()

    # ------------------------------------------------------------------ #
    # Enqueue
    # ------------------------------------------------------------------ #
    async def announce(
        self,
        text: str,
        *,
        kind: str = "progress",
        priority: int = int(Priority.PROGRESS),
        task_id: str | None = None,
        project_id: str | None = None,
    ) -> NarrationLine | None:
        """Queue a line. Returns the line, or ``None`` when it was dropped.

        Dropping is a normal outcome: a stale progress line, a duplicate, or a
        line the user has already moved past.
        """
        cleaned = " ".join((text or "").split())
        if not cleaned:
            return None

        if self.listening and priority >= int(Priority.PROGRESS):
            # The user is speaking: do not queue narration over them.
            self.dropped += 1
            return None

        async with self._lock:
            if self._history and self._history[-1].text == cleaned:
                self.dropped += 1
                return None

            line = NarrationLine(
                text=cleaned,
                kind=kind,
                priority=priority,
                task_id=task_id,
                project_id=project_id,
            )

            # A newer progress line supersedes a queued older one: announcing
            # "found the module" after "the tests pass" would be nonsense.
            if line.priority >= int(Priority.PROGRESS):
                self._queue = [
                    item for item in self._queue if item.priority < int(Priority.PROGRESS)
                ]

            self._sequence += 1
            line.sequence = self._sequence
            self._queue.append(line)

            if len(self._queue) > self._max_queue:
                # Drop the least urgent, oldest item first.
                self._queue.sort(key=lambda item: (item.priority, item.sequence))
                victim = self._queue.pop()
                self.dropped += 1
                logger.debug("narration queue full; dropped %r", victim.text)

        await self._publish(line, spoken=False)
        self._wake.set()
        return line

    async def interrupt(self, reason: str = "user") -> int:
        """Yield to the user: stop speech and clear lower-priority announcements.

        Called when the user starts speaking or presses the voice control.
        Returns how many queued lines were dropped.
        """
        self.listening = True
        with contextlib.suppress(Exception):
            await self._transport.stop()
        async with self._lock:
            dropped = len([item for item in self._queue if item.priority > int(Priority.CRITICAL)])
            self._queue = [item for item in self._queue if item.priority == int(Priority.CRITICAL)]
            self.dropped += dropped
        if dropped:
            logger.info("narration interrupted by %s; %d line(s) dropped", reason, dropped)
        await self._publish(
            NarrationLine(text="", kind="interrupt", priority=int(Priority.CRITICAL)),
            spoken=False,
            channel="voice",
            extra={"event": "interrupt", "reason": reason, "dropped": dropped},
        )
        return dropped

    async def resume(self) -> None:
        """The user has stopped speaking; narration may continue."""
        self.listening = False
        await self._publish(
            NarrationLine(text="", kind="resume", priority=int(Priority.CRITICAL)),
            spoken=False,
            channel="voice",
            extra={"event": "resume"},
        )

    # ------------------------------------------------------------------ #
    # Worker
    # ------------------------------------------------------------------ #
    async def _run(self) -> None:
        try:
            while True:
                await self._wake.wait()
                while True:
                    line = await self._take()
                    if line is None:
                        break
                    if self.listening and line.priority > int(Priority.CRITICAL):
                        self.dropped += 1
                        continue
                    try:
                        await self._transport.deliver(line)
                    except Exception:  # noqa: BLE001 - audio must never break the app
                        logger.warning("narration transport failed", exc_info=True)
                    async with self._lock:
                        self._history.append(line)
                        del self._history[:-20]
                    await self._publish(line, spoken=True)
                    if self._min_interval > 0:
                        await asyncio.sleep(self._min_interval)
                self._wake.clear()
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            logger.exception("narration worker stopped")

    async def _take(self) -> NarrationLine | None:
        async with self._lock:
            if not self._queue:
                return None
            self._queue.sort(key=lambda item: (item.priority, item.sequence))
            return self._queue.pop(0)

    # ------------------------------------------------------------------ #
    # Introspection
    # ------------------------------------------------------------------ #
    @property
    def transport(self) -> NarrationTransport:
        """The active transport, so the API can ask it for audio by line id."""
        return self._transport

    def recent(self, limit: int = 20) -> list[dict[str, Any]]:
        entries = [*self._history, *self._queue][-limit:]
        return [
            {**line.to_dict(), "spoken": line.spoken_at is not None}
            for line in sorted(entries, key=lambda item: item.sequence)
        ]

    def state(self) -> dict[str, Any]:
        return {
            "enabled": True,
            "transport": getattr(self._transport, "name", "unknown"),
            # A transport knows best: the ElevenLabs one reports whether it is
            # actually configured, not merely present.
            "audio_available": bool(
                getattr(self._transport, "audio_available", None)
                if getattr(self._transport, "audio_available", None) is not None
                else getattr(self._transport, "name", "") != "recording"
            ),
            "listening": self.listening,
            "queued": len(self._queue),
            "dropped": self.dropped,
            "spoken": len(self._history),
            "recent": self.recent(10),
        }

    async def _publish(
        self,
        line: NarrationLine,
        *,
        spoken: bool,
        channel: str = "narration",
        extra: dict[str, Any] | None = None,
    ) -> None:
        if self._bus is None:
            return
        payload = {**line.to_dict(), "spoken": spoken}
        if extra:
            payload.update(extra)
        with contextlib.suppress(Exception):
            await self._bus.publish({"channel": channel, "payload": payload})
