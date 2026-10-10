"""In-process publish/subscribe bus for real-time UI updates.

The bus is intentionally simple: an asyncio fan-out of JSON-serialisable
messages to any number of WebSocket subscribers. It holds no state that needs
persisting (that is the event repository's job), so a dropped subscriber never
loses data — the UI can always re-fetch from the REST API.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)


class EventBus:
    def __init__(self, *, queue_size: int = 500) -> None:
        self._queues: set[asyncio.Queue[dict[str, Any]]] = set()
        self._queue_size = queue_size
        self._lock = asyncio.Lock()

    async def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        """Register a new subscriber and return its queue."""
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=self._queue_size)
        async with self._lock:
            self._queues.add(queue)
        return queue

    async def unsubscribe(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        async with self._lock:
            self._queues.discard(queue)

    @property
    def subscriber_count(self) -> int:
        return len(self._queues)

    async def publish(self, payload: dict[str, Any]) -> None:
        """Deliver *payload* to every subscriber, dropping the oldest message
        on a slow subscriber rather than blocking the publisher."""
        async with self._lock:
            queues = list(self._queues)
        for queue in queues:
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                # Slow client: discard the oldest item and retry once.
                try:
                    queue.get_nowait()
                    queue.put_nowait(payload)
                except (asyncio.QueueEmpty, asyncio.QueueFull):  # pragma: no cover
                    logger.warning("dropping event for a slow WebSocket subscriber")
