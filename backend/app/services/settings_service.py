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

logger = logging.getLogger(__name__)

_OPENROUTER_KEY_URL = "https://openrouter.ai/api/v1/key"
_ELEVENLABS_USER_URL = "https://api.elevenlabs.io/v1/user"
_TEST_TIMEOUT = 15.0
_PI_CACHE_TTL = 60.0


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
        try:
            async with httpx.AsyncClient(timeout=_TEST_TIMEOUT) as client:
                response = await client.get(
                    _ELEVENLABS_USER_URL, headers={"xi-api-key": key}
                )
        except httpx.HTTPError as exc:
            return ConnectionTestResult(
                ok=False,
                message="Could not reach ElevenLabs.",
                detail=type(exc).__name__,
            )
        if response.status_code == 200:
            agent_id = await self.get_plain("elevenlabs_agent_id")
            if not agent_id:
                return ConnectionTestResult(
                    ok=False,
                    message=(
                        "ElevenLabs key is valid, but no Conversational Agent ID "
                        "is configured."
                    ),
                    detail="Voice conversations require an Agent ID.",
                )
            return ConnectionTestResult(
                ok=True,
                message="ElevenLabs key is valid and an Agent ID is configured.",
            )
        if response.status_code in (401, 403):
            return ConnectionTestResult(
                ok=False, message="ElevenLabs rejected the API key."
            )
        return ConnectionTestResult(
            ok=False, message=f"ElevenLabs returned HTTP {response.status_code}."
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
