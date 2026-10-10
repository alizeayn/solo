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
    OrchestratorStatusOut,
    SettingsUpdate,
)
from ..security import mask_secret
from ..services.openrouter import OpenRouterClient, OpenRouterError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/orchestrator", tags=["orchestrator"])


async def _status_payload(container: Container) -> OrchestratorStatusOut:
    config = await container.brain.configuration()
    key = await container.settings_service.get_secret("openrouter_api_key")
    return OrchestratorStatusOut(
        enabled=bool(config["enabled"]),
        configured=bool(config["configured"]),
        has_key=bool(config["has_key"]),
        model=config["model"],
        key_masked=mask_secret(key),
        call_count=int(config["call_count"]),
        failure_count=int(config["failure_count"]),
        last_error=config["last_error"],
        last_latency_ms=config["last_latency_ms"],
        last_model=config["last_model"],
    )


async def _require_client(container: Container) -> tuple[OpenRouterClient, str | None]:
    pair = await container.brain.client()
    if pair is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "The Orchestrator needs an OpenRouter API key. Add one in the "
                "Orchestrator settings first."
            ),
        )
    return pair


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
    if payload.model is not None:
        values["openrouter_model"] = payload.model
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
    """Every model OpenRouter exposes for the saved key."""
    client, _saved = await _require_client(container)
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
    key = await container.settings_service.get_secret("openrouter_api_key")
    if not key:
        return ConnectionTestResult(
            ok=False,
            state="not_configured",
            message="No OpenRouter API key is saved.",
            detail="Add a key in the Orchestrator settings, then test again.",
        )

    client = OpenRouterClient(
        key,
        base_url=container.settings.openrouter_base_url,
        timeout=container.settings.orchestrator_timeout_seconds,
    )
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
            message="The OpenRouter key is valid.",
            detail=detail or None,
        )

    target = model or await container.settings_service.get_plain("openrouter_model")
    if not target:
        return ConnectionTestResult(
            ok=True,
            state="configured",
            message="The OpenRouter key is valid, but no Orchestrator model is selected.",
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
