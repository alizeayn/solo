"""Pi Agent configuration endpoints.

Everything the Settings UI needs to manage Pi without a terminal: provider
listing, credential entry (written through Pi's own ``auth.json``), readiness
checks, model discovery, catalog refresh and a real end-to-end validation.

Secrets are write-only. No response contains a credential value.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query, status

from ..deps import ContainerDep, CurrentUser
from ..schemas import (
    ConnectionTestResult,
    PiAuthOut,
    PiCatalogRefreshOut,
    PiCredentialIn,
    PiModelOut,
    PiProviderOut,
    PiRuntimeOut,
    PiStatusOut,
)
from ..adapters.pi_rpc import PiRpcError, PiTimeoutError, PiUnavailableError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/pi", tags=["pi"])


async def _status(container: ContainerDep) -> PiStatusOut:
    service = container.pi_config
    runtime = await service.runtime()
    saved = service.saved_credentials()

    return PiStatusOut(
        runtime=PiRuntimeOut(
            available=runtime.available,
            version=runtime.version,
            executable=runtime.executable,
            agent_dir=runtime.agent_dir,
            detail=runtime.detail,
        ),
        backend=container.backend_name,
        provider=await container.settings_service.get_plain("pi_provider"),
        model=await container.settings_service.get_plain("pi_model"),
        thinking_level=await container.settings_service.get_plain("pi_thinking_level"),
        approve_project=await container.settings_service.get_bool("pi_approve_project", False),
        minimal_harness=container.settings.pi_minimal_harness,
        agent_dir=str(service.agent_dir()),
        auth_file=str(service.auth_file()),
        configured_providers=sorted(saved.keys()),
        sessions=container.orchestrator.sessions(),
    )


@router.get("/status", response_model=PiStatusOut)
async def pi_status(container: ContainerDep, _: CurrentUser) -> PiStatusOut:
    return await _status(container)


@router.get("/providers", response_model=list[PiProviderOut])
async def list_providers(container: ContainerDep, _: CurrentUser) -> list[PiProviderOut]:
    providers = await container.pi_config.list_providers()
    return [PiProviderOut.model_validate(item.to_dict()) for item in providers]


@router.get("/models", response_model=list[PiModelOut])
async def list_models(
    container: ContainerDep,
    _: CurrentUser,
    provider: str | None = Query(default=None),
    refresh: bool = Query(default=False),
) -> list[PiModelOut]:
    try:
        models = await container.pi_config.list_models(provider=provider, refresh=refresh)
    except PiUnavailableError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except (PiRpcError, PiTimeoutError) as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    return [PiModelOut.model_validate(model.to_dict()) for model in models]


@router.post("/models/refresh", response_model=PiCatalogRefreshOut)
async def refresh_models(
    container: ContainerDep, _: CurrentUser
) -> PiCatalogRefreshOut:
    """Run ``pi update --models`` to refresh Pi's model catalogs."""
    result = await container.pi_config.refresh_catalog()
    return PiCatalogRefreshOut.model_validate(result)


@router.get("/providers/{provider}/auth", response_model=PiAuthOut)
async def provider_auth(
    provider: str, container: ContainerDep, _: CurrentUser
) -> PiAuthOut:
    check = await container.pi_config.auth_check(provider)
    return PiAuthOut.model_validate(check.to_dict())


@router.put("/providers/{provider}/credential", response_model=PiAuthOut)
async def save_credential(
    provider: str,
    payload: PiCredentialIn,
    container: ContainerDep,
    _: CurrentUser,
) -> PiAuthOut:
    """Store an API key for a provider, exactly as ``/login`` would."""
    if not container.pi_config.executable():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Pi is not installed, so its credentials cannot be written.",
        )
    try:
        container.pi_config.save_credential(provider, payload.api_key)
    except (ValueError, OSError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Could not save the credential: {exc}",
        ) from exc
    check = await container.pi_config.auth_check(provider)
    logger.info("saved Pi credential for %s (status=%s)", provider, check.status)
    return PiAuthOut.model_validate(check.to_dict())


@router.delete("/providers/{provider}/credential", response_model=PiAuthOut)
async def delete_credential(
    provider: str, container: ContainerDep, _: CurrentUser
) -> PiAuthOut:
    removed = container.pi_config.delete_credential(provider)
    if not removed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No saved credential for {provider}.",
        )
    check = await container.pi_config.auth_check(provider)
    return PiAuthOut.model_validate(check.to_dict())


@router.post("/providers/{provider}/credential/from-orchestrator", response_model=PiAuthOut)
async def credential_from_orchestrator(
    provider: str, container: ContainerDep, _: CurrentUser
) -> PiAuthOut:
    """Copy Solo's Orchestrator OpenRouter key into Pi's credential store.

    Implements the "reuse the OpenRouter key instead of entering it twice"
    option: the key is read from Solo's encrypted store and written through Pi's
    own mechanism, never returned to the browser.
    """
    key = await container.settings_service.get_secret("openrouter_api_key")
    if not key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "No OpenRouter key is saved for the Orchestrator yet. Add one in "
                "the Orchestrator section first."
            ),
        )
    try:
        container.pi_config.save_credential(provider, key)
    except (ValueError, OSError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Could not save the credential: {exc}",
        ) from exc
    check = await container.pi_config.auth_check(provider)
    return PiAuthOut.model_validate(check.to_dict())


@router.post("/providers/{provider}/test", response_model=ConnectionTestResult)
async def test_provider(
    provider: str,
    container: ContainerDep,
    _: CurrentUser,
    model: str | None = Query(default=None),
    deep: bool = Query(
        default=False,
        description=(
            "Run one minimal real generation to prove the provider accepts the "
            "credential. Slower and may cost a few tokens."
        ),
    ),
) -> ConnectionTestResult:
    """Validate a provider configuration.

    ``deep=false`` only checks that a credential is present — it never reports a
    provider as *verified*. ``deep=true`` performs a real request.
    """
    result = await container.pi_config.validate_provider(provider, model=model, deep=deep)
    return ConnectionTestResult.model_validate(result)
