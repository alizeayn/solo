"""Voice endpoints.

Solo's product direction is voice-native: the conversation is the interface and
speech is its primary output. These endpoints expose the **narration pipeline** —
what Solo would say, in what order, and whether it is currently yielding to the
user.

Audio itself arrives in Phase 4 (ElevenLabs). The default transport records
rather than speaks, so `audio_available` is false and the UI says so; the
ordering, coalescing, rate limiting and barge-in behaviour this exposes is real
and is exercised by the tests.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from ..deps import ContainerDep, CurrentUser

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/voice", tags=["voice"])


class InterruptRequest(BaseModel):
    reason: str = Field(default="user", max_length=64)


@router.get("/state", response_model=dict)
async def voice_state(container: ContainerDep, _: CurrentUser) -> dict[str, Any]:
    """What the voice channel is doing, and what it recently said."""
    state = container.narration.state()
    settings = await container.settings_service.orchestrator_settings()
    state["voice_enabled"] = await container.settings_service.get_bool(
        "voice_enabled", True
    )
    state["speech_enabled"] = await container.settings_service.get_bool(
        "progress_speech_enabled", True
    )
    state["orchestrator_model"] = settings.get("model")
    # Be explicit about the boundary: the pipeline is real, the audio is not.
    state["phase"] = "narration-foundation"
    return state


@router.post("/interrupt", response_model=dict)
async def interrupt(
    payload: InterruptRequest, container: ContainerDep, _: CurrentUser
) -> dict[str, Any]:
    """Yield to the user: stop speech and drop lower-priority announcements.

    This is the barge-in path. The UI calls it when the user starts talking or
    presses the voice control, so narration never speaks over the person.
    """
    dropped = await container.narration.interrupt(payload.reason)
    logger.info("voice interrupted (%s): %d queued line(s) dropped", payload.reason, dropped)
    return {"dropped": dropped, **container.narration.state()}


@router.post("/resume", response_model=dict)
async def resume(container: ContainerDep, _: CurrentUser) -> dict[str, Any]:
    """Resume narration after the user has finished speaking."""
    await container.narration.resume()
    return container.narration.state()


@router.get("/history", response_model=list[dict])
async def history(
    container: ContainerDep, _: CurrentUser, limit: int = 50
) -> list[dict[str, Any]]:
    """What Solo has said, and what it is about to say."""
    if limit < 1 or limit > 200:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="limit must be 1–200"
        )
    return container.narration.recent(limit)
