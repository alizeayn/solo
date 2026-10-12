"""Settings service: secret storage, masking and connection tests.

Invariants enforced here:
* Secret values are encrypted before they touch the database and are registered
  with the log redactor as soon as they are read.
* The API never returns a real secret — only ``configured`` + ``masked``.
* Setting a key to an empty string clears it.
"""

from __future__ import annotations

import logging
import time

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..adapters.pi_agent import probe_pi_runtime
from ..adapters.pi_session import PiLaunchConfig
from ..config import Settings
from ..domain import PLAIN_SETTING_KEYS, SECRET_SETTING_KEYS
from ..logging_setup import forget_secret, register_secret
from ..repositories import SettingsRepository
from ..schemas import (
    ConnectionTestResult,
    SecretStatus,
    SettingsOut,
    SettingsUpdate,
)
from ..security import SecretCipher, mask_secret
from .elevenlabs import (
    DEFAULT_BASE_URL,
    DEFAULT_STT_MODEL,
    DEFAULT_TTS_MODEL,
    ElevenLabsClient,
    ElevenLabsConfig,
    ElevenLabsError,
)

logger = logging.getLogger(__name__)

_OPENROUTER_KEY_URL = "https://openrouter.ai/api/v1/key"
_ELEVENLABS_USER_URL = "https://api.elevenlabs.io/v1/user"
_TEST_TIMEOUT = 15.0
_PI_CACHE_TTL = 60.0
_VOICE_CACHE_TTL = 300.0


class SettingsService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        cipher: SecretCipher,
        settings: Settings,
    ) -> None:
        self._session_factory = session_factory
        self._cipher = cipher
        self._settings = settings
        self._pi_cache: tuple[float, object] | None = None
        self._voice_cache: tuple[float, str | None] | None = None
        self._voice_names: tuple[float, dict[str, str]] | None = None

    # ------------------------------------------------------------------ #
    # Reading
    # ------------------------------------------------------------------ #
    async def get_secret(self, key: str) -> str | None:
        async with self._session_factory() as session:
            record = await SettingsRepository(session).get(key)
        if record is None or not record.value:
            return None
        value = self._cipher.try_decrypt(record.value)
        if value:
            register_secret(value)
        return value

    async def get_plain(self, key: str, default: str | None = None) -> str | None:
        async with self._session_factory() as session:
            record = await SettingsRepository(session).get(key)
        if record is None or record.value is None:
            return default
        return record.value

    async def get_bool(self, key: str, default: bool = False) -> bool:
        raw = await self.get_plain(key)
        if raw is None:
            return default
        return raw.lower() in {"1", "true", "yes", "on"}

    async def status(self, *, refresh_pi: bool = False) -> SettingsOut:
        """Return masked settings suitable for the UI."""
        async with self._session_factory() as session:
            records = {r.key: r for r in await SettingsRepository(session).all()}

        def secret_status(key: str) -> SecretStatus:
            record = records.get(key)
            if record is None or not record.value:
                return SecretStatus(configured=False, masked=None)
            plain = self._cipher.try_decrypt(record.value)
            return SecretStatus(configured=True, masked=mask_secret(plain))

        def plain(key: str, default=None):
            record = records.get(key)
            return record.value if record and record.value is not None else default

        pi_info = await self._pi_info(refresh=refresh_pi)

        return SettingsOut(
            openrouter_api_key=secret_status("openrouter_api_key"),
            elevenlabs_api_key=secret_status("elevenlabs_api_key"),
            openrouter_model=plain("openrouter_model"),
            elevenlabs_agent_id=plain("elevenlabs_agent_id"),
            elevenlabs_tts_voice_id=plain("elevenlabs_tts_voice_id"),
            elevenlabs_model_id=plain("elevenlabs_model_id")
            or DEFAULT_TTS_MODEL,
            elevenlabs_stt_model_id=plain("elevenlabs_stt_model_id")
            or DEFAULT_STT_MODEL,
            elevenlabs_voice_name=await self._voice_name(),
            pi_provider=plain("pi_provider"),
            pi_model=plain("pi_model"),
            pi_base_url=plain("pi_base_url"),
            pi_thinking_level=plain("pi_thinking_level"),
            pi_approve_project=plain("pi_approve_project", "false") == "true",
            pi_reuse_openrouter_key=plain("pi_reuse_openrouter_key", "false") == "true",
            orchestrator_enabled=plain("orchestrator_enabled", "true") == "true",
            checks_enabled=plain("checks_enabled", "true") == "true",
            voice_enabled=plain("voice_enabled", "true") == "true",
            progress_speech_enabled=plain("progress_speech_enabled", "true") == "true",
            pi_version=pi_info.version,
            pi_rpc_available=pi_info.rpc_supported,
            theme=plain("theme", "dark") or "dark",
        )

    # ------------------------------------------------------------------ #
    # Pi Agent configuration
    # ------------------------------------------------------------------ #
    async def pi_launch_config(self) -> PiLaunchConfig:
        """The launch configuration for the Pi subprocess, from saved settings."""
        return PiLaunchConfig(
            provider=(await self.get_plain("pi_provider")) or None,
            model=(await self.get_plain("pi_model")) or None,
            thinking_level=(await self.get_plain("pi_thinking_level")) or None,
            approve_project=await self.get_bool("pi_approve_project", False),
            minimal_harness=self._settings.pi_minimal_harness,
        )

    async def voice_status(self) -> dict[str, Any]:
        """The voice configuration, from the store only — **never the network**.

        This backs ``GET /api/voice/state``, which the UI reads while a task is
        running. Resolving the full configuration here would call ElevenLabs to
        discover a voice, putting a third-party HTTP request (with a 30s timeout)
        on a frequently-polled endpoint. That is how a healthy backend still
        makes the whole workspace look dead: the browser's connection pool fills
        with hung requests and every other panel stops updating.

        Anything needing the network belongs behind an explicit action —
        saving settings, testing the connection, or retrieving models.
        """
        key = await self.get_secret("elevenlabs_api_key")
        model_id = await self.get_plain("elevenlabs_model_id") or DEFAULT_TTS_MODEL
        stt_model_id = await self.get_plain("elevenlabs_stt_model_id") or DEFAULT_STT_MODEL
        voice_id = await self.get_plain("elevenlabs_tts_voice_id")

        # A name is only ever reported from what has already been fetched.
        cached = self._voice_names
        voice_name = (
            cached[1].get(voice_id) if cached and voice_id else None
        )

        return {
            "configured": bool(key),
            "audio_available": bool(key and voice_id),
            # Distinct from "no key": a scoped key cannot list voices, so a voice
            # has to be chosen by hand.
            "needs_voice": bool(key and not voice_id),
            "model_id": model_id,
            "stt_model_id": stt_model_id,
            "voice_id": voice_id,
            "voice_name": voice_name,
        }

    async def voice_config(self) -> ElevenLabsConfig | None:
        """Resolved voice configuration, or ``None`` when not configured.

        Resolved per line rather than cached at startup, so saving a key
        or choosing a model takes effect on the next thing Solo says.
        When no voice has been chosen yet, the first voice on the
        account is used — a hardcoded voice id might not exist for a
        given account, and naming an unknown voice fails at synthesis
        time rather than at configuration time.
        """
        key = await self.get_secret("elevenlabs_api_key")
        if not key:
            return None
        voice_id = await self.get_plain("elevenlabs_tts_voice_id")
        if not voice_id:
            voice_id = await self._first_voice_id(key)
        if not voice_id:
            return None
        model_id = (
            await self.get_plain("elevenlabs_model_id") or DEFAULT_TTS_MODEL
        )
        return ElevenLabsConfig(
            client=self.elevenlabs_client(key),
            voice_id=voice_id,
            model_id=model_id,
        )

    def elevenlabs_client(self, key: str) -> ElevenLabsClient:
        return ElevenLabsClient(
            key,
            base_url=self._settings.elevenlabs_base_url,
            timeout=self._settings.elevenlabs_timeout_seconds,
        )

    async def _first_voice_id(self, key: str) -> str | None:
        # Cached briefly: one lookup, not one per spoken line.
        now = time.monotonic()
        cached = self._voice_cache
        if cached is not None and now - cached[0] < _VOICE_CACHE_TTL:
            return cached[1]
        try:
            voices = await self.elevenlabs_client(key).list_voices(limit=1)
        except Exception:  # noqa: BLE001 - never break a task over a voice
            # Cache the failure too. A key scoped without `voices_read` fails
            # every time, and retrying on every state poll would hammer the API
            # to learn the same thing.
            logger.debug("could not list voices", exc_info=True)
            self._voice_cache = (now, None)
            return None
        voice_id = voices[0].id if voices else None
        self._voice_cache = (now, voice_id)
        return voice_id

    async def voice_name(self) -> str | None:
        """The selected voice's display name. Never raises, never blocks voice."""
        return await self._voice_name()

    async def _voice_name(self) -> str | None:
        """The selected voice's name, for display only. Never raises."""
        voice_id = await self.get_plain("elevenlabs_tts_voice_id")
        if not voice_id:
            return None
        key = await self.get_secret("elevenlabs_api_key")
        if not key:
            return None
        now = time.monotonic()
        if self._voice_names and now - self._voice_names[0] < _VOICE_CACHE_TTL:
            return self._voice_names[1].get(voice_id)
        try:
            voices = await self.elevenlabs_client(key).list_voices()
        except Exception:  # noqa: BLE001
            return None
        mapping = {voice.id: voice.name for voice in voices}
        self._voice_names = (now, mapping)
        return mapping.get(voice_id)

    async def orchestrator_settings(self) -> dict[str, Any]:
        """OpenRouter configuration for the Orchestrator (never the key)."""
        return {
            "enabled": await self.get_bool("orchestrator_enabled", True),
            "model": await self.get_plain("openrouter_model"),
        }

    # ------------------------------------------------------------------ #
    # Writing
    # ------------------------------------------------------------------ #
    async def update(self, payload: SettingsUpdate) -> SettingsOut:
        provided = payload.model_dump(exclude_unset=True)
        async with self._session_factory() as session:
            repo = SettingsRepository(session)
            for key, value in provided.items():
                if key in SECRET_SETTING_KEYS:
                    if value is None:
                        continue
                    if value == "":
                        await repo.set(key, None, is_secret=True)
                        continue
                    register_secret(value)
                    await repo.set(key, self._cipher.encrypt(value), is_secret=True)
                elif key in PLAIN_SETTING_KEYS:
                    if value is None:
                        await repo.set(key, None, is_secret=False)
                    elif isinstance(value, bool):
                        await repo.set(key, "true" if value else "false", is_secret=False)
                    else:
                        await repo.set(key, str(value), is_secret=False)
            await session.commit()
        # Force the next status() to re-probe Pi (config may have changed).
        self._pi_cache = None
        return await self.status(refresh_pi=True)

    async def clear_secret(self, key: str) -> SettingsOut:
        if key not in SECRET_SETTING_KEYS:
            raise KeyError(key)
        existing = await self.get_secret(key)
        forget_secret(existing)
        async with self._session_factory() as session:
            await SettingsRepository(session).set(key, None, is_secret=True)
            await session.commit()
        return await self.status()

    # ------------------------------------------------------------------ #
    # Connection tests
    # ------------------------------------------------------------------ #
    async def test_openrouter(self) -> ConnectionTestResult:
        key = await self.get_secret("openrouter_api_key")
        if not key:
            return ConnectionTestResult(
                ok=False,
                message="No OpenRouter API key is configured.",
                detail="Add a key in Settings, then test again.",
            )
        try:
            async with httpx.AsyncClient(timeout=_TEST_TIMEOUT) as client:
                response = await client.get(
                    _OPENROUTER_KEY_URL,
                    headers={"Authorization": f"Bearer {key}"},
                )
        except httpx.HTTPError as exc:
            return ConnectionTestResult(
                ok=False,
                message="Could not reach OpenRouter.",
                detail=type(exc).__name__,
            )
        if response.status_code == 200:
            label = ""
            try:
                data = response.json().get("data", {})
                label = data.get("label") or ""
            except ValueError:
                pass
            return ConnectionTestResult(
                ok=True, message=f"OpenRouter key is valid{(' (' + label + ')') if label else ''}."
            )
        if response.status_code in (401, 403):
            return ConnectionTestResult(
                ok=False, message="OpenRouter rejected the API key."
            )
        return ConnectionTestResult(
            ok=False, message=f"OpenRouter returned HTTP {response.status_code}."
        )

    async def test_elevenlabs(self) -> ConnectionTestResult:
        key = await self.get_secret("elevenlabs_api_key")
        if not key:
            return ConnectionTestResult(
                ok=False,
                message="No ElevenLabs API key is configured.",
                detail="Add a key in Settings, then test again.",
            )
        # Validate against an endpoint the integration actually needs, not
        # /v1/user. A key can be entirely valid for speech while being scoped
        # without `user_read`, and calling that "rejected" would be a lie that
        # sends the user off to regenerate a working key.
        client = self.elevenlabs_client(key)
        try:
            models = await client.list_models()
        except ElevenLabsError as exc:
            return ConnectionTestResult(
                ok=False,
                state=exc.code or "failed",
                message=str(exc),
                detail=exc.detail,
            )

        tts = [model for model in models if model.can_tts]
        model_id = await self.get_plain("elevenlabs_model_id") or DEFAULT_TTS_MODEL
        saved_voice = await self.get_plain("elevenlabs_tts_voice_id")

        # Voice discovery needs `voices_read`, which not every key has. Not being
        # able to *list* voices is not the same as not being able to speak: a
        # voice id can be set directly, and on a free plan library voices are
        # refused anyway.
        voices: list = []
        voice_note = ""
        try:
            voices = await client.list_voices(limit=5)
        except ElevenLabsError as exc:
            voice_note = (
                "This key cannot list voices (needs the voices_read permission), "
                "so set a voice id directly."
                if exc.code == "missing_permissions"
                else f"Voices could not be listed: {exc}"
            )

        voice_id = saved_voice or (voices[0].id if voices else None)
        if not voice_id:
            return ConnectionTestResult(
                ok=False,
                state="needs_voice",
                message=(
                    "The ElevenLabs key works and models are readable, but no "
                    "voice is selected and voices cannot be listed."
                ),
                detail=voice_note or "Choose a voice in the ElevenLabs dashboard.",
                model=model_id,
            )

        detail = f"Selected model: {model_id}"
        if voice_note:
            detail = f"{detail}. {voice_note}"
        return ConnectionTestResult(
            ok=True,
            state="configured",
            message=(
                f"ElevenLabs key is valid — {len(tts)} speech model(s) available "
                f"to this account."
            ),
            detail=detail,
            model=model_id,
        )

    async def test_pi(self) -> ConnectionTestResult:
        info = await probe_pi_runtime(self._settings)
        if not info.available:
            return ConnectionTestResult(ok=False, message=info.detail)
        return ConnectionTestResult(
            ok=True,
            message=f"Pi CLI detected: {info.version or 'unknown version'}.",
            detail=info.detail,
        )

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    async def _pi_info(self, *, refresh: bool = False):
        now = time.monotonic()
        if not refresh and self._pi_cache and now - self._pi_cache[0] < _PI_CACHE_TTL:
            return self._pi_cache[1]
        info = await probe_pi_runtime(self._settings)
        self._pi_cache = (now, info)
        return info
