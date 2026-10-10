"""Pi Agent configuration: providers, credentials and model discovery.

Everything here reuses Pi's own interfaces rather than re-implementing them:

* **Credentials** are written to Pi's ``auth.json`` — the same file ``/login``
  writes. This is required for correctness, not just convention: an existing
  ``auth.json`` entry takes precedence over a provider environment variable
  (verified), so injecting ``OPENROUTER_API_KEY`` alone would not make the
  credential chosen in Solo effective.
* **Readiness** comes from ``pi auth check --provider X --json``.
* **Models** come from the RPC ``get_available_models`` command, which returns
  Pi's fully resolved model definitions.
* **Catalog refresh** runs ``pi update --models``.

Secrets never leave the backend: ``auth.json`` is read only for *key names* and
never returned to the browser, and the API exposes only
``{configured: true, masked: "****abcd"}``.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..config import Settings
from ..adapters.pi_agent import PiRuntimeInfo, probe_pi_runtime
from ..adapters.pi_events import provider_error_text
from ..adapters.pi_rpc import PiRpcClient, PiRpcError, PiUnavailableError, PiTimeoutError

logger = logging.getLogger(__name__)

#: How long a one-shot Pi RPC probe may take (model catalog, state).
PROBE_TIMEOUT = 150.0
#: How long `pi update --models` may take.
CATALOG_REFRESH_TIMEOUT = 300.0
#: Cap on models returned to the UI in one response.
MAX_MODELS = 2000
#: Credentials Solo writes are always API keys; OAuth flows need a terminal.
CREDENTIAL_TYPE = "api_key"


@dataclass(frozen=True)
class ProviderInfo:
    """A provider Pi knows about, with the environment variable it reads."""

    id: str
    label: str
    env_var: str | None = None


#: Curated from Pi 1.1.0's own provider registry (ids and API-key environment
#: variables verified against the installed build, not guessed). Used to offer
#: providers in the UI that have no model catalog yet, and as a manual fallback
#: when automatic model discovery is not possible.
KNOWN_PROVIDERS: tuple[ProviderInfo, ...] = (
    ProviderInfo("openrouter", "OpenRouter", "OPENROUTER_API_KEY"),
    ProviderInfo("anthropic", "Anthropic", "ANTHROPIC_API_KEY"),
    ProviderInfo("openai", "OpenAI", "OPENAI_API_KEY"),
    ProviderInfo("google", "Google Gemini", "GEMINI_API_KEY"),
    ProviderInfo("google-vertex", "Google Vertex AI", "GOOGLE_CLOUD_API_KEY"),
    ProviderInfo("deepseek", "DeepSeek", "DEEPSEEK_API_KEY"),
    ProviderInfo("xai", "xAI", "XAI_API_KEY"),
    ProviderInfo("mistral", "Mistral", "MISTRAL_API_KEY"),
    ProviderInfo("groq", "Groq", "GROQ_API_KEY"),
    ProviderInfo("cerebras", "Cerebras", "CEREBRAS_API_KEY"),
    ProviderInfo("nvidia", "NVIDIA NIM", "NVIDIA_API_KEY"),
    ProviderInfo("together", "Together AI", "TOGETHER_API_KEY"),
    ProviderInfo("fireworks", "Fireworks AI", "FIREWORKS_API_KEY"),
    ProviderInfo("baseten", "Baseten", "BASETEN_API_KEY"),
    ProviderInfo("deepinfra", "DeepInfra", "DEEPINFRA_API_KEY"),
    ProviderInfo("huggingface", "Hugging Face", "HF_TOKEN"),
    ProviderInfo("moonshot", "Moonshot AI", "MOONSHOT_API_KEY"),
    ProviderInfo("minimax", "MiniMax", "MINIMAX_API_KEY"),
    ProviderInfo("qwen", "Qwen", "QWEN_TOKEN_PLAN_API_KEY"),
    ProviderInfo("zai", "ZAI Coding Plan", "ZAI_API_KEY"),
    ProviderInfo("xiaomi", "Xiaomi MiMo", "XIAOMI_API_KEY"),
    ProviderInfo("kimi", "Kimi For Coding", "KIMI_API_KEY"),
    ProviderInfo("meta", "Meta", "META_API_KEY"),
    ProviderInfo("ant-ling", "Ant Ling", "ANT_LING_API_KEY"),
    ProviderInfo("vercel-ai-gateway", "Vercel AI Gateway", "AI_GATEWAY_API_KEY"),
    ProviderInfo("opencode", "OpenCode Zen / Go", "OPENCODE_API_KEY"),
    ProviderInfo("opencode-go", "OpenCode Go", "OPENCODE_API_KEY"),
    ProviderInfo("typesafe", "TypeSafe (classifier models)", "TYPESAFE_API_KEY"),
    ProviderInfo("radius", "Radius (Earendil)", "RADIUS_API_KEY"),
    ProviderInfo("github-copilot", "GitHub Copilot", "COPILOT_GITHUB_TOKEN"),
    ProviderInfo("azure", "Azure OpenAI", "AZURE_OPENAI_API_KEY"),
    ProviderInfo("amazon-bedrock", "Amazon Bedrock", None),
    ProviderInfo("cloudflare-workers-ai", "Cloudflare Workers AI", "CLOUDFLARE_API_KEY"),
    ProviderInfo("cloudflare-ai-gateway", "Cloudflare AI Gateway", "CLOUDFLARE_API_KEY"),
)

_KNOWN_BY_ID = {info.id: info for info in KNOWN_PROVIDERS}


@dataclass
class ModelInfo:
    id: str
    name: str
    provider: str
    reasoning: bool = False
    context_window: int | None = None
    max_tokens: int | None = None
    input_modalities: list[str] = field(default_factory=list)
    cost: dict[str, float] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "provider": self.provider,
            "reasoning": self.reasoning,
            "context_window": self.context_window,
            "max_tokens": self.max_tokens,
            "input_modalities": self.input_modalities,
            "cost": self.cost,
        }


@dataclass
class AuthCheck:
    provider: str
    status: str  # ready | not_ready | unknown
    auth_type: str | None = None
    reason: str | None = None
    detail: str | None = None

    @property
    def ready(self) -> bool:
        return self.status == "ready"

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "status": self.status,
            "auth_type": self.auth_type,
            "reason": self.reason,
            "detail": self.detail,
            "ready": self.ready,
        }


@dataclass
class ProviderStatus:
    id: str
    label: str
    env_var: str | None
    configured: bool
    auth_type: str | None
    source: str  # saved | environment | oauth | none
    model_count: int
    model_count_known: bool
    in_catalog: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "env_var": self.env_var,
            "configured": self.configured,
            "auth_type": self.auth_type,
            "source": self.source,
            "model_count": self.model_count,
            "model_count_known": self.model_count_known,
            "in_catalog": self.in_catalog,
        }


class PiConfigService:
    """Reads and writes Pi's configuration through Pi's own interfaces."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._model_cache: tuple[float, list[ModelInfo]] | None = None
        self._model_cache_ttl = 120.0

    # ------------------------------------------------------------------ #
    # Paths
    # ------------------------------------------------------------------ #
    def agent_dir(self) -> Path:
        """Pi's agent directory (``PI_CODING_AGENT_DIR`` or ``~/.pi/agent``)."""
        override = (self._settings.pi_agent_dir or "").strip()
        if override:
            return Path(override).expanduser()
        return Path(
            os.environ.get("PI_CODING_AGENT_DIR", str(Path.home() / ".pi" / "agent"))
        ).expanduser()

    def auth_file(self) -> Path:
        return self.agent_dir() / "auth.json"

    def settings_file(self) -> Path:
        return self.agent_dir() / "settings.json"

    def executable(self) -> str | None:
        return shutil.which(self._settings.pi_executable)

    async def runtime(self) -> PiRuntimeInfo:
        return await probe_pi_runtime(executable=self._settings.pi_executable)

    # ------------------------------------------------------------------ #
    # auth.json (never exposes values)
    # ------------------------------------------------------------------ #
    def saved_credentials(self) -> dict[str, dict[str, Any]]:
        """Return ``{provider: {type, has_key, env_keys}}`` — never the key."""
        path = self.auth_file()
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        if not isinstance(raw, dict):
            return {}
        result: dict[str, dict[str, Any]] = {}
        for provider, entry in raw.items():
            if not isinstance(entry, dict):
                continue
            result[str(provider)] = {
                "type": str(entry.get("type") or "unknown"),
                "has_key": bool(entry.get("key")),
                "env_keys": sorted((entry.get("env") or {}).keys())
                if isinstance(entry.get("env"), dict)
                else [],
            }
        return result

    def _write_auth(self, payload: dict[str, Any]) -> None:
        path = self.auth_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        # Atomic write so an interrupted save cannot corrupt Pi's credentials.
        handle, temporary = tempfile.mkstemp(
            dir=str(path.parent), prefix=".auth-", suffix=".json"
        )
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as sink:
                json.dump(payload, sink, indent=2)
                sink.write("\n")
            os.chmod(temporary, 0o600)
            os.replace(temporary, path)
        except BaseException:
            Path(temporary).unlink(missing_ok=True)
            raise

    def save_credential(self, provider: str, api_key: str) -> None:
        """Store an API key exactly as ``/login`` would."""
        provider = provider.strip()
        if not provider:
            raise ValueError("provider is required")
        if not api_key.strip():
            raise ValueError("api key is required")
        path = self.auth_file()
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                payload = {}
        except (OSError, ValueError):
            payload = {}
        entry = payload.get(provider)
        if not isinstance(entry, dict):
            entry = {}
        entry["type"] = CREDENTIAL_TYPE
        entry["key"] = api_key.strip()
        payload[provider] = entry
        self._write_auth(payload)
        logger.info("stored Pi credential for provider %s", provider)

    def delete_credential(self, provider: str) -> bool:
        path = self.auth_file()
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return False
        if not isinstance(payload, dict) or provider not in payload:
            return False
        del payload[provider]
        self._write_auth(payload)
        logger.info("removed Pi credential for provider %s", provider)
        return True

    def masked_credential(self, provider: str) -> str | None:
        """Never returns the key — only whether one is present."""
        entry = self.saved_credentials().get(provider)
        if not entry or not entry.get("has_key"):
            return None
        return "stored"

    # ------------------------------------------------------------------ #
    # CLI helpers
    # ------------------------------------------------------------------ #
    async def _run_cli(
        self, args: list[str], *, timeout: float
    ) -> tuple[int, str, str]:
        executable = self.executable()
        if executable is None:
            raise PiUnavailableError(
                "the 'pi' executable was not found on PATH"
            )
        env = dict(os.environ)
        env["PI_SKIP_VERSION_CHECK"] = "1"
        if self._settings.pi_agent_dir:
            env["PI_CODING_AGENT_DIR"] = str(self.agent_dir())
        process = await asyncio.create_subprocess_exec(
            executable,
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            process.kill()
            raise PiTimeoutError(f"'{args[0]}' did not finish within {timeout:g}s") from None
        return (
            process.returncode or 0,
            stdout.decode("utf-8", "replace"),
            stderr.decode("utf-8", "replace"),
        )

    def _probe_argv(self) -> list[str]:
        return [
            self._settings.pi_executable,
            "--mode",
            "rpc",
            "--no-session",
            "--no-approve",
            "--no-extensions",
            "--no-skills",
            "--no-prompt-templates",
            "--no-mcp",
            "--no-context-files",
        ]

    async def _rpc_probe(
        self, command: dict[str, Any], *, timeout: float = PROBE_TIMEOUT
    ) -> dict[str, Any]:
        """Run one RPC command in a short-lived Pi process."""
        probe_dir = self._settings.app_data_dir / "pi" / "probe"
        probe_dir.mkdir(parents=True, exist_ok=True)
        env: dict[str, str] = {"PI_SKIP_VERSION_CHECK": "1"}
        if self._settings.pi_agent_dir:
            env["PI_CODING_AGENT_DIR"] = str(self.agent_dir())
        client = PiRpcClient(
            self._probe_argv(),
            cwd=str(probe_dir),
            env=env,
            label="pi-probe",
        )
        await client.start()
        try:
            return await client.call(command, timeout=timeout)
        finally:
            await client.close(grace=3.0)

    # ------------------------------------------------------------------ #
    # Auth checks
    # ------------------------------------------------------------------ #
    async def auth_check(self, provider: str) -> AuthCheck:
        """Ask Pi whether a provider is authenticated."""
        if self.executable() is None:
            return AuthCheck(
                provider=provider,
                status="unknown",
                reason="pi_not_installed",
                detail="The 'pi' executable was not found on PATH.",
            )
        try:
            _rc, stdout, stderr = await self._run_cli(
                ["auth", "check", "--provider", provider, "--no-refresh", "--json"],
                timeout=60.0,
            )
        except (PiUnavailableError, PiTimeoutError) as exc:
            return AuthCheck(provider=provider, status="unknown", detail=str(exc))

        payload: dict[str, Any] = {}
        text = stdout.strip()
        if text.startswith("{"):
            try:
                payload = json.loads(text)
            except ValueError:
                payload = {}
        status = str(payload.get("status") or "unknown")
        reason = payload.get("reason")
        detail = None
        if status != "ready" and not reason:
            detail = (stderr.strip() or text)[:300] or None
        return AuthCheck(
            provider=provider,
            status=status,
            auth_type=payload.get("authType"),
            reason=str(reason) if reason else None,
            detail=detail,
        )

    # ------------------------------------------------------------------ #
    # Models
    # ------------------------------------------------------------------ #
    @staticmethod
    def _parse_model(raw: dict[str, Any]) -> ModelInfo:
        cost = raw.get("cost")
        return ModelInfo(
            id=str(raw.get("id") or ""),
            name=str(raw.get("name") or raw.get("id") or ""),
            provider=str(raw.get("provider") or ""),
            reasoning=bool(raw.get("reasoning")),
            context_window=raw.get("contextWindow"),
            max_tokens=raw.get("maxTokens"),
            input_modalities=list(raw.get("input") or []),
            cost=cost if isinstance(cost, dict) else None,
        )

    async def list_models(
        self, *, provider: str | None = None, refresh: bool = False
    ) -> list[ModelInfo]:
        """Pi's resolved model catalog, optionally filtered by provider."""
        now = time.monotonic()
        if (
            not refresh
            and self._model_cache is not None
            and now - self._model_cache[0] < self._model_cache_ttl
        ):
            models = self._model_cache[1]
        else:
            data = await self._rpc_probe({"type": "get_available_models"})
            raw_models = data.get("models") or []
            models = [self._parse_model(item) for item in raw_models if isinstance(item, dict)]
            models = [model for model in models if model.id]
            self._model_cache = (now, models)
            logger.info("Pi reported %d available models", len(models))

        if provider:
            wanted = provider.strip().lower()
            models = [m for m in models if m.provider.lower() == wanted]
        return models[:MAX_MODELS]

    async def refresh_catalog(self) -> dict[str, Any]:
        """Run ``pi update --models`` and invalidate the cache."""
        try:
            rc, stdout, stderr = await self._run_cli(
                ["update", "--models"], timeout=CATALOG_REFRESH_TIMEOUT
            )
        except (PiUnavailableError, PiTimeoutError) as exc:
            return {"ok": False, "message": str(exc), "output": None}
        self._model_cache = None
        output = (stdout or stderr).strip()[-800:]
        if rc == 0:
            return {
                "ok": True,
                "message": "Model catalog refreshed from the providers.",
                "output": output or None,
            }
        return {
            "ok": False,
            "message": f"'pi update --models' exited with code {rc}.",
            "output": output or None,
        }

    # ------------------------------------------------------------------ #
    # Providers
    # ------------------------------------------------------------------ #
    async def list_providers(
        self, *, include_models: bool = True
    ) -> list[ProviderStatus]:
        """Every provider Solo can offer, annotated with real status."""
        saved = self.saved_credentials()
        catalog: dict[str, int] = {}
        catalog_error: str | None = None

        if include_models:
            try:
                for model in await self.list_models():
                    catalog[model.provider] = catalog.get(model.provider, 0) + 1
            except (PiRpcError, PiUnavailableError, PiTimeoutError, OSError) as exc:
                catalog_error = str(exc)
                logger.warning("model catalog unavailable: %s", exc)

        known_ids = {info.id for info in KNOWN_PROVIDERS}
        extra_ids = sorted(set(catalog) - known_ids - {""})

        entries: list[ProviderInfo] = list(KNOWN_PROVIDERS) + [
            ProviderInfo(pid, pid.replace("-", " ").title()) for pid in extra_ids
        ]

        statuses: list[ProviderStatus] = []
        for info in entries:
            entry = saved.get(info.id) or {}
            env_set = bool(info.env_var and os.environ.get(info.env_var))
            auth_type = entry.get("type")
            configured = bool(entry.get("has_key")) or bool(auth_type) or env_set
            if entry.get("has_key"):
                source = "saved"
            elif auth_type and auth_type != CREDENTIAL_TYPE:
                source = "oauth"
            elif env_set:
                source = "environment"
            else:
                source = "none"
            statuses.append(
                ProviderStatus(
                    id=info.id,
                    label=info.label,
                    env_var=info.env_var,
                    configured=configured,
                    auth_type=auth_type,
                    source=source,
                    model_count=catalog.get(info.id, 0),
                    model_count_known=catalog_error is None,
                    in_catalog=info.id in catalog,
                )
            )

        # Providers with credentials or models first, then alphabetical.
        statuses.sort(key=lambda s: (not s.configured, not s.in_catalog, s.label.lower()))
        return statuses

    # ------------------------------------------------------------------ #
    # Validation
    # ------------------------------------------------------------------ #
    async def validate_provider(
        self,
        provider: str,
        *,
        model: str | None = None,
        deep: bool = False,
    ) -> dict[str, Any]:
        """Validate a provider configuration.

        ``deep=False`` checks that Pi has a usable credential (free, fast).
        ``deep=True`` performs one minimal real generation, which is the only
        way to prove a credential is *accepted* by the provider rather than
        merely *present*. A provider is never reported as verified on the
        strength of a presence check alone.
        """
        started = time.monotonic()
        check = await self.auth_check(provider)
        if not check.ready:
            return {
                "ok": False,
                "state": "not_configured" if check.reason == "credentials_not_configured" else "failed",
                "message": _auth_failure_message(provider, check),
                "detail": check.detail,
                "provider": provider,
                "model": model,
                "auth_type": check.auth_type,
                "latency_ms": int((time.monotonic() - started) * 1000),
            }

        if not deep:
            return {
                "ok": True,
                "state": "configured",
                "message": (
                    f"{provider} has a usable credential. Run a real request to "
                    "confirm the provider accepts it."
                ),
                "detail": check.auth_type,
                "provider": provider,
                "model": model,
                "auth_type": check.auth_type,
                "latency_ms": int((time.monotonic() - started) * 1000),
            }

        if not model:
            return {
                "ok": False,
                "state": "failed",
                "message": "Choose a model before running a real request.",
                "detail": None,
                "provider": provider,
                "model": None,
                "auth_type": check.auth_type,
                "latency_ms": int((time.monotonic() - started) * 1000),
            }

        return await self._live_model_probe(
            provider, model, started=started
        )

    async def _live_model_probe(
        self, provider: str, model: str, *, started: float
    ) -> dict[str, Any]:
        """One minimal real generation, used to prove credentials work."""
        probe_dir = self._settings.app_data_dir / "pi" / "probe"
        probe_dir.mkdir(parents=True, exist_ok=True)
        env: dict[str, str] = {"PI_SKIP_VERSION_CHECK": "1"}
        if self._settings.pi_agent_dir:
            env["PI_CODING_AGENT_DIR"] = str(self.agent_dir())

        argv = self._probe_argv() + ["--provider", provider, "--model", model]
        errors: list[str] = []
        settled = asyncio.Event()
        stop_reasons: list[str] = []

        def on_record(record: dict[str, Any]) -> None:
            if record.get("type") == "agent_settled":
                settled.set()
                return
            if record.get("type") == "message_end":
                message = record.get("message") or {}
                if message.get("role") != "assistant":
                    return
                stop_reasons.append(str(message.get("stopReason")))
                if message.get("stopReason") == "error":
                    errors.append(provider_error_text(message))

        client = PiRpcClient(
            argv, cwd=str(probe_dir), env=env, on_event=on_record, label="pi-validate"
        )
        try:
            await client.start()
        except PiUnavailableError as exc:
            return {
                "ok": False,
                "state": "failed",
                "message": str(exc),
                "detail": None,
                "provider": provider,
                "model": model,
                "latency_ms": int((time.monotonic() - started) * 1000),
            }
        try:
            await client.call(
                {
                    "type": "prompt",
                    "message": "Reply with the single word: ok",
                },
                timeout=30.0,
            )
            try:
                await asyncio.wait_for(settled.wait(), timeout=120.0)
            except asyncio.TimeoutError:
                return {
                    "ok": False,
                    "state": "failed",
                    "message": "The provider did not respond within 120 seconds.",
                    "detail": None,
                    "provider": provider,
                    "model": model,
                    "latency_ms": int((time.monotonic() - started) * 1000),
                }
        except PiRpcError as exc:
            return {
                "ok": False,
                "state": "failed",
                "message": f"Pi rejected the request: {exc}",
                "detail": None,
                "provider": provider,
                "model": model,
                "latency_ms": int((time.monotonic() - started) * 1000),
            }
        finally:
            await client.close(grace=3.0)

        latency = int((time.monotonic() - started) * 1000)
        if errors:
            return {
                "ok": False,
                "state": "failed",
                "message": errors[-1],
                "detail": f"model={model}",
                "provider": provider,
                "model": model,
                "latency_ms": latency,
            }
        if not stop_reasons or stop_reasons[-1] == "error":
            return {
                "ok": False,
                "state": "failed",
                "message": "The provider returned no usable response.",
                "detail": f"model={model}",
                "provider": provider,
                "model": model,
                "latency_ms": latency,
            }
        return {
            "ok": True,
            "state": "verified",
            "message": f"{provider} / {model} answered a real request successfully.",
            "detail": f"stop_reason={stop_reasons[-1]}",
            "provider": provider,
            "model": model,
            "latency_ms": latency,
        }


def _auth_failure_message(provider: str, check: AuthCheck) -> str:
    if check.reason == "provider_not_found":
        return f"Pi does not recognise the provider '{provider}'."
    if check.reason == "credentials_not_configured":
        return f"No credential is configured for {provider}."
    if check.status == "unknown":
        return check.detail or f"Could not determine the status of {provider}."
    return f"{provider} is not ready ({check.reason or check.status})."
