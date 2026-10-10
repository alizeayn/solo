"""Application WebSocket: pushes normalised events to the browser.

Authentication uses the same session cookie as the REST API; a ``?token=``
query parameter is accepted as a fallback for non-browser clients. Sessions
that fail authentication are closed with code 4401 before any data is sent.
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..deps import COOKIE_NAME

logger = logging.getLogger(__name__)

router = APIRouter(tags=["ws"])

WS_UNAUTHORIZED = 4401


@router.websocket("/api/ws")
async def application_ws(websocket: WebSocket) -> None:
    container = websocket.app.state.container
    token = websocket.cookies.get(COOKIE_NAME) or websocket.query_params.get("token")
    user = await container.auth.resolve(token)
    if user is None:
        # Reject before accepting so no data can be read or written.
        await websocket.close(code=WS_UNAUTHORIZED)
        return

    await websocket.accept()
    queue = await container.bus.subscribe()
    try:
        await websocket.send_json(
            {
                "channel": "ready",
                "payload": {
                    "user": user.username,
                    "coding_agent": container.adapter_name,
                },
            }
        )
        while True:
            payload = await queue.get()
            await websocket.send_json(payload)
    except (WebSocketDisconnect, asyncio.CancelledError):
        pass
    except Exception:  # noqa: BLE001 - connection errors are expected
        logger.debug("websocket closed unexpectedly", exc_info=True)
    finally:
        await container.bus.unsubscribe(queue)
