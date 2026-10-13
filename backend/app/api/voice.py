"""Voice endpoints: narration state, speech input, speech output, and questions.

Solo is voice-native: the conversation is the interface and speech is its primary
output. These endpoints expose the whole loop:

* **Narration state and history** — what Solo would say, in what order, and
  whether it is currently yielding to the user.
* **Model and voice discovery** — what the configured ElevenLabs account can
  actually use, so a model is chosen rather than assumed.
* **Transcription** — speech in. The transcript is returned; the caller posts it
  to the *existing* message endpoint, so intent classification, task creation,
  Pi Agent execution and milestones are all unchanged.
* **Audio** — speech out, one MP3 per narration line, fetched by line id.
* **Questions** — answered from real task state, never invented.

Two boundaries are stated explicitly rather than implied:

* Speech *output* attaches at the transport seam ``NarrationService`` already
  defined, so nothing above it changes.
* When a question cannot be answered from what is known, the answer says so.
  The voice channel does not guess.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, File, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel, Field

from ..deps import ContainerDep, CurrentUser
from ..services.narration import Priority
from ..services.elevenlabs import (
    DEFAULT_STT_MODEL,
    DEFAULT_TTS_MODEL,
    REALTIME_STT_MODEL,
    REALTIME_STT_URL,
    ElevenLabsError,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/voice", tags=["voice"])

#: Refuse anything larger: an utterance, not a recording.
MAX_UTTERANCE_BYTES = 25 * 1024 * 1024


class InterruptRequest(BaseModel):
    reason: str = Field(default="user", max_length=64)


class VoiceSettingsIn(BaseModel):
    """Voice-specific configuration. Secrets go through ``/api/settings``."""

    model_id: str | None = None
    voice_id: str | None = None
    stt_model_id: str | None = None


# --------------------------------------------------------------------------- #
# Narration state
# --------------------------------------------------------------------------- #
async def _state_payload(container: ContainerDep) -> dict[str, Any]:
    """Everything the voice channel is currently doing.

    Deliberately **free of network I/O**. This is polled while a task runs, so a
    third-party call here would stall the whole workspace. The resolved
    configuration is only needed when Solo actually speaks, which happens off the
    critical path in the transport.
    """
    state = dict(container.narration.state())
    status = await container.settings_service.voice_status()

    state["voice_enabled"] = await container.settings_service.get_bool(
        "voice_enabled", True
    )
    state["speech_enabled"] = await container.settings_service.get_bool(
        "progress_speech_enabled", True
    )
    state.update(status)

    # Deliberately NOT an OR of the two sources. `voice_status()` reports whether
    # Solo is *configured* to speak; narration reports whether speaking actually
    # *works*. An account with an exhausted quota is both configured and silent,
    # and OR-ing them reported "voice-active" while every request returned 401 —
    # which is exactly how a broken integration looked healthy.
    narration_state = container.narration.state()
    state["voice_configured"] = bool(status.get("audio_available"))
    # Audio is available when Solo is *configured* to speak (a key, a model and a
    # voice) and the last attempt did not fail. Derived from the configuration
    # plus the recorded failure rather than from the transport's internal flag,
    # which only means "a configuration has been resolved at least once" and so
    # reads false before the first delivery even on a perfectly good account.
    state["audio_available"] = (
        state["voice_configured"] and narration_state.get("audio_error") is None
    )
    state["audio_error"] = narration_state.get("audio_error")
    state["speech_failures"] = narration_state.get("failed", 0)
    # "narration-only" is a working mode, not a failure: milestones still reach
    # the user as text, they are simply not spoken aloud.
    state["phase"] = "voice-active" if state["audio_available"] else "narration-only"
    return state


@router.get("/state", response_model=dict)
async def voice_state(container: ContainerDep, _: CurrentUser) -> dict[str, Any]:
    """What the voice channel is doing, and what it recently said."""
    return await _state_payload(container)


@router.post("/stt-token", response_model=dict)
async def stt_token(
    container: ContainerDep, _: CurrentUser
) -> dict[str, Any]:
    """Mint a single-use token for browser-side realtime transcription.

    The ElevenLabs API key never leaves the server; the browser receives a token
    scoped to one Realtime Speech-to-Text session. Returns ``available: false``
    with a readable reason instead of failing, so the UI can fall back to the
    batch transcriber and say why.
    """
    try:
        config = await container.settings_service.voice_config()
    except Exception as exc:  # noqa: BLE001 - report, never break the panel
        logger.warning("realtime voice unavailable: %s", exc)
        return {"available": False, "reason": str(exc), "token": None}

    if config is None:
        return {
            "available": False,
            "reason": (
                "No ElevenLabs key is configured, so realtime voice needs setup "
                "in Settings \u203a Voice."
            ),
            "token": None,
        }

    try:
        token = await config.client.create_realtime_token()
    except Exception as exc:  # noqa: BLE001
        logger.warning("could not mint a realtime token: %s", exc)
        return {"available": False, "reason": str(exc), "token": None}

    return {
        "available": True,
        "reason": None,
        "token": token,
        # The browser needs these to open the socket; neither is a secret.
        "model_id": REALTIME_STT_MODEL,
        "url": REALTIME_STT_URL,
    }


class SayRequest(BaseModel):
    """A line to speak that belongs to the conversation, not to a task."""

    text: str = Field(min_length=1, max_length=600)
    kind: str = Field(default="reply", max_length=24)


@router.post("/say", response_model=dict)
async def say(
    payload: SayRequest, container: ContainerDep, _: CurrentUser
) -> dict[str, Any]:
    """Speak a line through the normal narration pipeline.

    Used for the opening greeting and other conversational lines. Routing them
    through the same channel as milestone updates means one synthesis path, one
    WebSocket stream and one player, rather than a second mechanism that would
    drift from the first.

    ``IMPORTANT`` priority keeps the line above routine progress, and it is below
    ``PROGRESS`` in the barge-in check only in the sense that matters: an
    acknowledgement is never dropped just because the user is still speaking.
    """
    line = await container.narration.announce(
        payload.text,
        kind=payload.kind,
        priority=int(Priority.IMPORTANT),
    )
    # `state()` already has a `queued` key meaning "how many lines are pending",
    # so the outcome of this call is nested rather than flattened on top of it.
    return {
        "queued": line is not None,
        "id": line.id if line is not None else None,
        "state": container.narration.state(),
    }


@router.post("/interrupt", response_model=dict)
async def interrupt(
    payload: InterruptRequest, container: ContainerDep, _: CurrentUser
) -> dict[str, Any]:
    """Yield to the user: stop speech and drop lower-priority announcements.

    This is the barge-in path. The UI calls it when the user starts talking or
    presses the voice control, so narration never speaks over the person.
    """
    dropped = await container.narration.interrupt(payload.reason)
    logger.info(
        "voice interrupted (%s): %d queued line(s) dropped", payload.reason, dropped
    )
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
            status_code=status.HTTP_400_BAD_REQUEST, detail="limit must be 1-200"
        )
    return container.narration.recent(limit)


# --------------------------------------------------------------------------- #
# Speech output
# --------------------------------------------------------------------------- #
@router.get("/audio/{line_id}")
async def audio(line_id: str, container: ContainerDep, _: CurrentUser) -> Response:
    """The synthesised MP3 for one narration line.

    Returning 404 for an unknown id is the honest answer: a line with no audio
    is one the transport could not (or was not configured to) speak.
    """
    transport = container.narration.transport
    getter = getattr(transport, "audio_for", None)
    if not callable(getter):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="speech output is not available",
        )
    found = getter(line_id)
    if found is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="no audio for that line",
        )
    data, mime = found
    return Response(
        content=data,
        media_type=mime,
        headers={"Cache-Control": "private, max-age=300"},
    )


# --------------------------------------------------------------------------- #
# Discovery
# --------------------------------------------------------------------------- #
async def _elevenlabs_client(container: ContainerDep):
    """A client for the saved key, or a clear 400 naming the real cause."""
    key = await container.settings_service.get_secret("elevenlabs_api_key")
    if not key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "No ElevenLabs API key is saved. Add one in "
                "Settings -> Voice, then retrieve models."
            ),
        )
    return container.settings_service.elevenlabs_client(key)


@router.get("/models", response_model=list[dict])
async def list_models(container: ContainerDep, _: CurrentUser) -> list[dict[str, Any]]:
    """Speech models the configured account can use.

    Real discovery from ``GET /v1/models``, not a hardcoded catalog: an alpha
    model the account can use appears, and one it cannot is absent.
    """
    client = await _elevenlabs_client(container)
    try:
        models = await client.list_models()
    except ElevenLabsError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
        ) from exc
    return [model.to_dict() for model in models]


@router.get("/voices", response_model=list[dict])
async def list_voices(
    container: ContainerDep, _: CurrentUser, limit: int = Query(default=100, ge=1, le=100)
) -> list[dict[str, Any]]:
    """Voices available to the account, so a voice is chosen not pasted."""
    client = await _elevenlabs_client(container)
    try:
        voices = await client.list_voices(limit=limit)
    except ElevenLabsError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
        ) from exc
    return [voice.to_dict() for voice in voices]


@router.put("/settings", response_model=dict)
async def update_voice_settings(
    payload: VoiceSettingsIn, container: ContainerDep, _: CurrentUser
) -> dict[str, Any]:
    """Save the selected model and voice.

    This writes the same settings the runtime reads, so the selection is not
    merely displayed: the next line Solo speaks uses it.
    """
    updates: dict[str, str] = {}
    if payload.model_id is not None:
        updates["elevenlabs_model_id"] = payload.model_id
    if payload.voice_id is not None:
        updates["elevenlabs_tts_voice_id"] = payload.voice_id
    if payload.stt_model_id is not None:
        updates["elevenlabs_stt_model_id"] = payload.stt_model_id
    if updates:
        from ..schemas import SettingsUpdate

        await container.settings_service.update(SettingsUpdate(**updates))
    return await _state_payload(container)


# --------------------------------------------------------------------------- #
# Speech input
# --------------------------------------------------------------------------- #
@router.post("/transcribe", response_model=dict)
async def transcribe(
    container: ContainerDep,
    _: CurrentUser,
    file: UploadFile = File(...),
    language_code: str | None = Query(default=None, max_length=16),
) -> dict[str, Any]:
    """Turn one recorded utterance into text.

    The transcript is returned and *not* dispatched: the caller posts it to
    ``POST /api/projects/{id}/messages``, which is the same path a typed message
    takes. Transcription therefore adds a way to produce text, not a second way
    to run a task.
    """
    client = await _elevenlabs_client(container)
    audio = await file.read()
    if not audio:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The recording was empty.",
        )
    if len(audio) > MAX_UTTERANCE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Recordings must be under {MAX_UTTERANCE_BYTES // (1024 * 1024)} MB.",
        )

    model_id = (
        await container.settings_service.get_plain("elevenlabs_stt_model_id")
    ) or DEFAULT_STT_MODEL
    try:
        transcript = await client.transcribe(
            audio,
            filename=file.filename or "utterance.webm",
            model_id=model_id,
            language_code=language_code,
        )
    except ElevenLabsError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
        ) from exc
    return transcript.to_dict()