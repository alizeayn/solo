"""Settings endpoints.

All routes require authentication. Outbound payloads contain only masked
secret status; raw keys are never returned or logged.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from ..deps import ContainerDep, CurrentUser
from ..domain import SECRET_SETTING_KEYS
from ..schemas import ConnectionTestResult, SettingsOut, SettingsUpdate

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("", response_model=SettingsOut)
async def read_settings(container: ContainerDep, _: CurrentUser) -> SettingsOut:
    return await container.settings_service.status()


@router.put("", response_model=SettingsOut)
async def update_settings(
    payload: SettingsUpdate, container: ContainerDep, _: CurrentUser
) -> SettingsOut:
    return await container.settings_service.update(payload)


@router.delete("/secret/{key}", response_model=SettingsOut)
async def delete_secret(
    key: str, container: ContainerDep, _: CurrentUser
) -> SettingsOut:
    if key not in SECRET_SETTING_KEYS:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="unknown secret key"
        )
    return await container.settings_service.clear_secret(key)


@router.post("/test/{provider}", response_model=ConnectionTestResult)
async def test_provider(
    provider: str, container: ContainerDep, _: CurrentUser
) -> ConnectionTestResult:
    """Actively validate a provider configuration."""
    service = container.settings_service
    if provider == "openrouter":
        return await service.test_openrouter()
    if provider == "elevenlabs":
        return await service.test_elevenlabs()
    if provider == "pi":
        return await service.test_pi()
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail="unknown provider"
    )
