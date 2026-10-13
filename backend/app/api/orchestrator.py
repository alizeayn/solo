"""Orchestrator endpoints: OpenRouter configuration, models and validation.

The Orchestrator model handles intent detection, task prioritisation, state
management and progress summarisation. These endpoints let the Settings UI
configure it end to end without a terminal, and let the UI distinguish clearly
between *saved*, *validated* and *failed*.
"""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter, HTTPException, Query, status

from ..container import Container
from ..deps import ContainerDep, CurrentUser
from ..schemas import (
    ConnectionTestResult,
    OpenRouterModelOut,
    OrchestratorConfigIn,
    OrchestratorProviderOut,
    OrchestratorStatusOut,
    SettingsUpdate,
)
from ..security import mask_secret
from ..services.openrouter import OpenRouterClient, OpenRouterError
from ..services.orchestrator_providers import (
    OPENROUTER,
    ProviderSpec,
    build_headers,
    get_provider,
    provider_catalog,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/orchestrator", tags=["orchestrator"])


async def _status_payload(container: Container) -> OrchestratorStatusOut:
    config = await container.brain.configuration()
    spec = await container.brain.active_provider()
    # The masked key belongs to whichever provider is active; showing
    # OpenRouter's mask while OpenCode Go is selected would be a lie.
    key = await container.settings_service.get_secret(spec.key_setting)
    return OrchestratorStatusOut(
        enabled=bool(config["enabled"]),
        configured=bool(config["configured"]),
        has_key=bool(config["has_key"]),
        model=config["model"],
        provider=str(config.get("provider") or spec.id),
        provider_label=str(config.get("provider_label") or spec.label),
        base_url=config.get("base_url"),
        key_masked=mask_secret(key),
        call_count=int(config["call_count"]),
        failure_count=int(config["failure_count"]),
        last_error=config["last_error"],
        last_latency_ms=config["last_latency_ms"],
        last_model=config["last_model"],
    )


async def _require_credentials(container: Container) -> tuple[OpenRouterClient, str | None]:
    """A client for calls that need a key but not a chosen model.

    Model *listing* is exactly that: you cannot choose a model before you can see
    the list. The error messages are deliberately distinct, so "no key" is never
    reported when the real problem is a missing model or a disabled Orchestrator.
    """
    spec = await container.brain.active_provider()
    enabled = await container.brain.is_enabled()
    if not enabled and not await _has_key(container):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"The Orchestrator is disabled and has no API key. Enable it and add "
                f"an {spec.label} API key in Settings \u203a Orchestrator."
            ),
        )
    pair = await container.brain.credentials()
    if pair is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"No {spec.label} API key is saved. Add one in Settings "
                f"\u203a Orchestrator, then retrieve models."
            ),
        )
    return pair


async def _has_key(container: Container) -> bool:
    spec = await container.brain.active_provider()
    return bool(await container.settings_service.get_secret(spec.key_setting))


@router.get("/providers", response_model=list[OrchestratorProviderOut])
async def list_providers(container: ContainerDep, _: CurrentUser) -> list[OrchestratorProviderOut]:
    """Every provider the Orchestrator supports, and whether each is ready.

    Reported per provider so the settings UI can say "OpenRouter is ready, OpenCode
    Go needs a key" instead of showing one global state that hides which provider
    is broken.
    """
    active = await container.brain.active_provider()
    out: list[OrchestratorProviderOut] = []
    for entry in provider_catalog():
        spec = get_provider(str(entry["id"]))
        key = await container.settings_service.get_secret(spec.key_setting)
        model = await container.settings_service.get_plain(spec.model_setting)
        out.append(
            OrchestratorProviderOut(
                **entry,
                configured=bool(key and model),
                has_key=bool(key),
                model=model,
                key_masked=mask_secret(key),
            )
        )
    # The active provider first, so the UI does not have to sort it.
    out.sort(key=lambda item: item.id != active.id)
    return out


@router.get("/status", response_model=OrchestratorStatusOut)
async def orchestrator_status(
    container: ContainerDep, _: CurrentUser
) -> OrchestratorStatusOut:
    return await _status_payload(container)


@router.put("/config", response_model=OrchestratorStatusOut)
async def update_config(
    payload: OrchestratorConfigIn, container: ContainerDep, _: CurrentUser
) -> OrchestratorStatusOut:
    values: dict[str, object] = {}
    if payload.provider is not None:
        spec = get_provider(payload.provider)
        if spec.id != payload.provider.strip().lower():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown provider: {payload.provider}",
            )
        values["orchestrator_provider"] = spec.id
    if payload.model is not None:
        # Models are provider-specific, so the id is written to the active
        # provider's own setting. Writing OpenRouter's id while OpenCode Go is
        # selected would configure a model that provider has never heard of.
        spec = get_provider(payload.provider) if payload.provider else await container.brain.active_provider()
        values[spec.model_setting] = payload.model
    if payload.enabled is not None:
        values["orchestrator_enabled"] = payload.enabled
    if values:
        await container.settings_service.update(SettingsUpdate(**values))
    return await _status_payload(container)


@router.get("/models", response_model=list[OpenRouterModelOut])
async def list_models(
    container: ContainerDep,
    _: CurrentUser,
    search: str | None = Query(default=None, description="Substring filter"),
) -> list[OpenRouterModelOut]:
    """Every model the active provider exposes for the saved key."""
    client, _saved = await _require_credentials(container)
    try:
        models = await client.list_models()
    except OpenRouterError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
        ) from exc

    if search:
        needle = search.strip().lower()
        models = [
            model
            for model in models
            if needle in model.id.lower() or needle in model.name.lower()
        ]

    return [
        OpenRouterModelOut(
            id=model.id,
            name=model.name,
            context_length=model.context_length,
            supports_structured_output=model.supports_structured_output,
            pricing=model.pricing,
        )
        for model in models
    ]


@router.post("/test", response_model=ConnectionTestResult)
async def test_orchestrator(
    container: ContainerDep,
    _: CurrentUser,
    model: str | None = Query(
        default=None, description="Override the saved model for this check"
    ),
    deep: bool = Query(
        default=True,
        description="Perform a real completion so the model is actually exercised.",
    ),
) -> ConnectionTestResult:
    """Validate the Orchestrator key and, with ``deep=true``, the model itself.

    A key is only ever reported as *verified* after a real completion succeeds.
    """
    spec = await container.brain.active_provider()
    key = await container.settings_service.get_secret(spec.key_setting)
    if not key:
        return ConnectionTestResult(
            ok=False,
            state="not_configured",
            message=f"No {spec.label} API key is saved.",
            detail="Add a key in the Orchestrator settings, then test again.",
        )

    client = OpenRouterClient(
        key,
        base_url=await container.brain._base_url(spec),
        timeout=container.settings.orchestrator_timeout_seconds,
        extra_headers=build_headers(spec, container.brain.session_id),
    )

    # Only OpenRouter exposes an account endpoint (`GET /key`). Asking OpenCode Go
    # for it would report a working key as broken, so the account check is
    # provider-specific and its absence is not treated as a fault.
    detail: str | None = None
    if spec.id == OPENROUTER:
        try:
            account = await client.verify_key()
        except OpenRouterError as exc:
            return ConnectionTestResult(
                ok=False, state="failed", message=str(exc), detail=exc.detail
            )
        label = account.get("label") or ""
        usage = account.get("usage")
        detail = ", ".join(
            part
            for part in (
                f"label={label}" if label else None,
                f"usage=${usage}" if isinstance(usage, (int, float)) else None,
            )
            if part
        )
        if not deep:
            return ConnectionTestResult(
                ok=True,
                state="configured",
                message=f"The {spec.label} key is valid.",
                detail=detail or None,
            )

    target = model or await container.settings_service.get_plain(spec.model_setting)
    if not target:
        return ConnectionTestResult(
            ok=True,
            state="configured",
            message=f"The {spec.label} key is valid, but no Orchestrator model is selected.",
            detail=detail or None,
        )

    started = time.monotonic()
    try:
        await client.complete_json(
            model=target,
            system="Respond with JSON only.",
            user='Return exactly this object: {"status":"ok"}',
            schema={
                "type": "object",
                "properties": {"status": {"type": "string"}},
                "required": ["status"],
                "additionalProperties": False,
            },
            schema_name="probe",
            max_tokens=64,
        )
    except OpenRouterError as exc:
        return ConnectionTestResult(
            ok=False,
            state="failed",
            message=str(exc),
            detail=exc.detail,
            model=target,
            latency_ms=int((time.monotonic() - started) * 1000),
        )

    return ConnectionTestResult(
        ok=True,
        state="verified",
        message=f"The Orchestrator model '{target}' answered a real request.",
        detail=detail or None,
        model=target,
        latency_ms=int((time.monotonic() - started) * 1000),
    )
