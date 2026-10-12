"""ElevenLabs client: speech synthesis and speech recognition.

Solo uses exactly two ElevenLabs capabilities, and deliberately not a third:

* **Text to speech** (`POST /v1/text-to-speech/{voice_id}/stream`) — to say the
  lines the narration pipeline already selected. This attaches at the transport
  seam `NarrationService` defined, so nothing above it changes.
* **Speech to text** (`POST /v1/speech-to-text`) — to turn the user's speech into
  text, which is then posted to the *existing* dispatch endpoint. Transcription
  therefore feeds the same path as typing, and intent classification, task
  creation, Pi Agent execution and milestones are all unchanged.
* **Not** the Agents Platform. It owns the conversation loop and the language
  model, which would put an ElevenLabs agent in front of Solo's Orchestrator and
  let it answer from its own context instead of from real task state.

Verified against the official documentation on 2026-10-11; see
`ElevenLabs Docs/` at the repository root for the notes and sources.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import httpx

logger = logging.getLogger(__name__)

#: Production endpoint. Regional residency hosts are documented in
#: ``ElevenLabs Docs/01-authentication.md`` and can be set per deployment.
DEFAULT_BASE_URL = "https://api.elevenlabs.io"

#: Fast, cheap synthesis for spoken progress. A milestone that arrives seconds
#: late is worse than one that sounds slightly less rich, and Flash v2.5 has a
#: ~75 ms median latency and a 40,000-character limit.
DEFAULT_TTS_MODEL = "eleven_flash_v2_5"
#: Highest-accuracy batch recognition model.
DEFAULT_STT_MODEL = "scribe_v2"
#: No subscription tier required, and ``audio/mpeg`` plays in every browser.
DEFAULT_OUTPUT_FORMAT = "mp3_44100_128"

#: Keep one synthesis request comfortably inside every model's character limit
#: (the smallest documented limit is 5,000 for ``eleven_v3``).
CHUNK_CHARS = 1800

_SENTENCE_END = re.compile(r"(?<=[.!?])\s+|\n{2,}")


class ElevenLabsError(RuntimeError):
    """A call to ElevenLabs failed.

    ``status`` is the HTTP status; ``code`` is the service's own machine-readable
    code (``missing_permissions``, ``paid_plan_required``, …) when it sent one,
    so a caller can distinguish "the key is wrong" from "the key is fine but not
    allowed to do this". ``detail`` is the human message. None of them ever
    contains the API key.
    """

    def __init__(
        self,
        message: str,
        *,
        status: int | None = None,
        detail: str | None = None,
        code: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.detail = detail
        self.code = code


@dataclass
class VoiceModel:
    """One entry from ``GET /v1/models``."""

    id: str
    name: str
    can_tts: bool = False
    can_voice_conversion: bool = False
    can_be_finetuned: bool = False
    max_text_length: int | None = None
    description: str | None = None
    languages: list[str] = field(default_factory=list)
    cost_multiplier: float | None = None
    requires_alpha: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "can_tts": self.can_tts,
            "can_voice_conversion": self.can_voice_conversion,
            "can_be_finetuned": self.can_be_finetuned,
            "max_text_length": self.max_text_length,
            "description": self.description,
            "languages": list(self.languages),
            "cost_multiplier": self.cost_multiplier,
            "requires_alpha": self.requires_alpha,
        }


@dataclass
class Voice:
    """One entry from ``GET /v2/voices``."""

    id: str
    name: str
    category: str | None = None
    description: str | None = None
    labels: dict[str, Any] = field(default_factory=dict)
    preview_url: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category,
            "description": self.description,
            "labels": dict(self.labels),
            "preview_url": self.preview_url,
        }


@dataclass
class Transcript:
    """The part of a transcription result Solo uses."""

    text: str
    language_code: str | None = None
    words: list[dict[str, Any]] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not self.text.strip()

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "language_code": self.language_code,
            "words": list(self.words),
            "empty": self.is_empty,
        }


def chunk_text(text: str, *, limit: int = CHUNK_CHARS) -> list[str]:
    """Split text into sentence-bounded pieces under ``limit`` characters.

    A milestone's detail is normally one sentence, so this exists for the
    exceptional case — a long summary read aloud — and never splits mid-word.
    """
    cleaned = " ".join((text or "").split())
    if not cleaned:
        return []
    if len(cleaned) <= limit:
        return [cleaned]

    chunks: list[str] = []
    current = ""
    for sentence in _SENTENCE_END.split(cleaned):
        piece = sentence.strip()
        if not piece:
            continue
        if not current:
            current = piece
        elif len(current) + 1 + len(piece) <= limit:
            current = f"{current} {piece}"
        else:
            chunks.append(current)
            current = piece
        # A single sentence longer than the limit still has to be split.
        while len(current) > limit:
            chunks.append(current[:limit].rstrip())
            current = current[limit:].lstrip()
    if current:
        chunks.append(current)
    return chunks


class ElevenLabsClient:
    """Thin, typed wrapper over the endpoints Solo uses."""

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 30.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._client = client

    # ------------------------------------------------------------------ #
    # Plumbing
    # ------------------------------------------------------------------ #
    @property
    def _headers(self) -> dict[str, str]:
        # ElevenLabs uses ``xi-api-key``, not a Bearer token.
        return {"xi-api-key": self._api_key}

    def _http(self) -> httpx.AsyncClient:
        if self._client is not None:
            return self._client
        return httpx.AsyncClient(timeout=self._timeout)

    async def _request(
        self, method: str, path: str, **kwargs: Any
    ) -> httpx.Response:
        owns = self._client is None
        client = self._http()
        try:
            response = await client.request(
                method, f"{self._base_url}{path}", headers=self._headers, **kwargs
            )
        except httpx.HTTPError as exc:
            raise ElevenLabsError(
                "Could not reach ElevenLabs.", detail=type(exc).__name__
            ) from exc
        finally:
            if owns:
                await client.aclose()
        return response

    @staticmethod
    def _error(response: httpx.Response) -> ElevenLabsError:
        """Turn a failed response into an error that names the real cause.

        ElevenLabs reports failures as ``{"detail": {...}}`` with a ``code``, a
        ``message`` and a finer-grained ``status``. The nested dict is the common
        case in practice, so it is handled first — reading only a string or a
        list, as this did, discards the real message and misreports every error.
        """
        detail: str | None = None
        code: str | None = None
        try:
            body = response.json()
        except ValueError:
            body = None

        if isinstance(body, dict):
            raw = body.get("detail")
            if isinstance(raw, dict):
                # {"detail": {"code": ..., "message": ..., "status": ...}}
                message = raw.get("message")
                detail = str(message) if message else None
                code = str(raw.get("status") or raw.get("code") or "") or None
            elif isinstance(raw, str):
                detail = raw
            elif isinstance(raw, list) and raw:
                first = raw[0]
                if isinstance(first, dict):
                    detail = str(first.get("msg") or "") or None
        elif isinstance(body, list) and body and isinstance(body[0], dict):
            detail = str(body[0].get("msg") or "") or None

        status = response.status_code
        if code == "missing_permissions" or (
            detail and "missing the permission" in detail
        ):
            # The key is *not* wrong. Saying "rejected" here would send the user
            # to regenerate a key that works.
            permission = ""
            if detail and "permission " in detail:
                permission = detail.split("permission ", 1)[1].split(" ", 1)[0].strip()
            message = (
                f"The ElevenLabs key is valid but is not permitted to "
                f"'{permission or 'perform this operation'}'."
            )
        elif status == 402 or code == "paid_plan_required":
            message = detail or "This ElevenLabs feature requires a paid plan."
        elif status in (401, 403):
            message = detail or "ElevenLabs rejected the API key."
        elif status == 422:
            message = "ElevenLabs rejected the request as invalid."
        elif status == 429:
            message = "ElevenLabs rate limit reached."
        elif status >= 500:
            message = f"ElevenLabs returned HTTP {status}."
        else:
            message = detail or f"ElevenLabs returned HTTP {status}."

        return ElevenLabsError(
            message, status=status, detail=detail, code=code
        )

    # ------------------------------------------------------------------ #
    # Account
    # ------------------------------------------------------------------ #
    async def verify_key(self) -> dict[str, Any]:
        """The account behind the key.

        Requires the ``user_read`` permission. Not all keys have it, which is
        why validation uses :meth:`list_models` instead: a key scoped for speech
        only is perfectly valid.
        """
        response = await self._request("GET", "/v1/user")
        if response.status_code != 200:
            raise self._error(response)
        try:
            data = response.json()
        except ValueError:
            return {}
        return data if isinstance(data, dict) else {}

    # ------------------------------------------------------------------ #
    # Models
    # ------------------------------------------------------------------ #
    async def list_models(self) -> list[VoiceModel]:
        """Models the *configured account* can use.

        Real discovery, not a hardcoded catalog: an alpha model an account has
        access to appears, and one it does not is absent.
        """
        response = await self._request("GET", "/v1/models")
        if response.status_code != 200:
            raise self._error(response)
        try:
            payload = response.json()
        except ValueError as exc:
            raise ElevenLabsError("ElevenLabs returned unreadable JSON.") from exc
        if not isinstance(payload, list):
            return []

        models: list[VoiceModel] = []
        for raw in payload:
            if not isinstance(raw, dict):
                continue
            model_id = raw.get("model_id") or raw.get("id")
            if not model_id:
                continue
            rates = raw.get("model_rates")
            multiplier = None
            if isinstance(rates, dict):
                value = rates.get("character_cost_multiplier")
                if isinstance(value, (int, float)):
                    multiplier = float(value)
            languages = [
                str(item.get("name") or item.get("language_id"))
                for item in (raw.get("languages") or [])
                if isinstance(item, dict)
            ]
            models.append(
                VoiceModel(
                    id=str(model_id),
                    name=str(raw.get("name") or model_id),
                    can_tts=bool(raw.get("can_do_text_to_speech")),
                    can_voice_conversion=bool(raw.get("can_do_voice_conversion")),
                    can_be_finetuned=bool(raw.get("can_be_finetuned")),
                    max_text_length=(
                        int(raw["maximum_text_length_per_request"])
                        if isinstance(
                            raw.get("maximum_text_length_per_request"), int
                        )
                        else None
                    ),
                    description=raw.get("description"),
                    languages=languages,
                    cost_multiplier=multiplier,
                    requires_alpha=bool(raw.get("requires_alpha_access")),
                )
            )
        models.sort(key=lambda item: (not item.can_tts, item.name.lower()))
        return models

    # ------------------------------------------------------------------ #
    # Voices
    # ------------------------------------------------------------------ #
    async def list_voices(self, *, limit: int = 100) -> list[Voice]:
        """Voices available to the account, so a voice is chosen not pasted."""
        response = await self._request(
            "GET",
            "/v2/voices",
            params={"page_size": max(1, min(limit, 100))},
        )
        if response.status_code != 200:
            raise self._error(response)
        try:
            payload = response.json()
        except ValueError as exc:
            raise ElevenLabsError("ElevenLabs returned unreadable JSON.") from exc
        raw_items = payload.get("voices") if isinstance(payload, dict) else payload
        if not isinstance(raw_items, list):
            return []

        voices: list[Voice] = []
        for raw in raw_items:
            if not isinstance(raw, dict):
                continue
            voice_id = raw.get("voice_id") or raw.get("id")
            if not voice_id:
                continue
            labels = raw.get("labels")
            voices.append(
                Voice(
                    id=str(voice_id),
                    name=str(raw.get("name") or voice_id),
                    category=raw.get("category"),
                    description=raw.get("description"),
                    labels=labels if isinstance(labels, dict) else {},
                    preview_url=raw.get("preview_url"),
                )
            )
        return voices

    # ------------------------------------------------------------------ #
    # Text to speech
    # ------------------------------------------------------------------ #
    async def synthesize(
        self,
        text: str,
        *,
        voice_id: str,
        model_id: str = DEFAULT_TTS_MODEL,
        output_format: str = DEFAULT_OUTPUT_FORMAT,
    ) -> tuple[bytes, str]:
        """Return ``(audio_bytes, mime_type)`` for one line of speech.

        Long text is split and concatenated, so a caller never has to know a
        model's character limit.
        """
        pieces = chunk_text(text)
        if not pieces:
            raise ElevenLabsError("There is nothing to say.")
        if not voice_id:
            raise ElevenLabsError(
                "No voice is selected.",
                detail="Choose a voice in Settings → Voice.",
            )

        buffers: list[bytes] = []
        for piece in pieces:
            response = await self._request(
                "POST",
                f"/v1/text-to-speech/{voice_id}/stream",
                params={"output_format": output_format},
                json={"text": piece, "model_id": model_id},
            )
            if response.status_code != 200:
                raise self._error(response)
            buffers.append(response.content)

        mime = "audio/mpeg" if output_format.startswith("mp3") else "audio/wav"
        return b"".join(buffers), mime

    # ------------------------------------------------------------------ #
    # Speech to text
    # ------------------------------------------------------------------ #
    async def transcribe(
        self,
        audio: bytes,
        *,
        filename: str = "utterance.webm",
        model_id: str = DEFAULT_STT_MODEL,
        language_code: str | None = None,
    ) -> Transcript:
        """Transcribe one recorded utterance.

        An empty transcript is a normal result — the user may not have spoken —
        and is returned rather than raised.
        """
        if not audio:
            raise ElevenLabsError(
                "No audio was received.", detail="The recording was empty."
            )
        data: dict[str, Any] = {"model_id": model_id}
        if language_code:
            data["language_code"] = language_code

        response = await self._request(
            "POST",
            "/v1/speech-to-text",
            data=data,
            files={"file": (filename, audio, "application/octet-stream")},
        )
        if response.status_code != 200:
            raise self._error(response)
        try:
            payload = response.json()
        except ValueError as exc:
            raise ElevenLabsError("ElevenLabs returned unreadable JSON.") from exc
        if not isinstance(payload, dict):
            return Transcript(text="")

        words = payload.get("words")
        return Transcript(
            text=str(payload.get("text") or ""),
            language_code=payload.get("language_code"),
            words=words if isinstance(words, list) else [],
        )


class ElevenLabsTransport:
    """A :class:`NarrationTransport` backed by ElevenLabs speech synthesis.

    Two properties matter more than the synthesis call itself:

    * **Nothing above this changes.** The narration service already decided what
      is worth saying, in what order, and when to yield. This only turns a line
      into audio.
    * **Audio failure never loses the line.** If synthesis fails, the line is
      still recorded and still shown in the UI; only the sound is missing. A
      task must not break because a voice was unavailable.

    Configuration is resolved **per line**, so saving a key, choosing a model or
    changing the voice takes effect on the next thing Solo says rather than at
    the next restart.
    """

    def __init__(
        self,
        config_provider: Any,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 30.0,
        keep: int = 24,
    ) -> None:
        #: ``async () -> ElevenLabsConfig | None``; ``None`` means "not configured".
        self._config_provider = config_provider
        self._base_url = base_url
        self._timeout = timeout
        self._keep = keep
        self._audio: dict[str, tuple[bytes, str]] = {}
        self._order: list[str] = []
        self._spoken: list[Any] = []
        self._configured = False
        self._stops = 0

    # ------------------------------------------------------------------ #
    # Introspection
    # ------------------------------------------------------------------ #
    @property
    def name(self) -> str:
        """Honest about the current mode, not about the intended one."""
        return "elevenlabs" if self._configured else "recording"

    @property
    def audio_available(self) -> bool:
        return self._configured

    @property
    def stops(self) -> int:
        return self._stops

    def audio_for(self, line_id: str) -> tuple[bytes, str] | None:
        return self._audio.get(line_id)

    def recent_lines(self) -> list[Any]:
        return list(self._spoken)

    # ------------------------------------------------------------------ #
    # Delivery
    # ------------------------------------------------------------------ #
    async def deliver(self, line: Any) -> None:
        config = await self._resolve()
        if config is None:
            # Not configured: behave exactly like the recording transport so the
            # pipeline stays observable and nothing is silently lost.
            self._configured = False
            self._remember(line)
            return

        self._configured = True
        try:
            audio, mime = await config.client.synthesize(
                line.text,
                voice_id=config.voice_id,
                model_id=config.model_id,
            )
        except ElevenLabsError as exc:
            # Keep the line; only the audio is missing.
            logger.info("elevenlabs synthesis failed: %s", exc)
            self._remember(line)
            return
        except Exception:  # noqa: BLE001 - audio must never break a task
            logger.warning("elevenlabs transport failed", exc_info=True)
            self._remember(line)
            return

        # Mark the line as spoken only once its audio exists. `spoken` is
        # what the player uses to decide whether there is anything to
        # fetch, so a line whose synthesis failed must report false
        # rather than sending the player after audio that was never made.
        line.spoken_at = datetime.now(timezone.utc).isoformat()
        self._store_audio(line.id, audio, mime)
        self._remember(line)

    async def stop(self) -> None:
        """Barge-in. Synthesis is one short request, so there is nothing to
        cancel server-side; the caller drops the audio it has not played yet."""
        self._stops += 1

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #
    async def _resolve(self) -> Any:
        try:
            return await self._config_provider()
        except Exception:  # noqa: BLE001
            logger.debug("could not resolve the voice configuration", exc_info=True)
            return None

    def _remember(self, line: Any) -> None:
        self._spoken.append(line)
        del self._spoken[: max(0, len(self._spoken) - 50)]

    def _store_audio(self, line_id: str, audio: bytes, mime: str) -> None:
        self._audio[line_id] = (audio, mime)
        self._order.append(line_id)
        while len(self._order) > self._keep:
            oldest = self._order.pop(0)
            self._audio.pop(oldest, None)


@dataclass
class ElevenLabsConfig:
    """Resolved voice configuration for one line of speech."""

    client: ElevenLabsClient
    voice_id: str
    model_id: str