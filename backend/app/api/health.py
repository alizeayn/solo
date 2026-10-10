"""Health endpoint. Intentionally public and free of secrets.

Exposes only liveness/readiness facts a load balancer or operator needs.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter
from sqlalchemy import text

from ..adapters.pi_agent import probe_pi_runtime
from ..deps import ContainerDep
from ..schemas import HealthOut

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health", response_model=HealthOut)
async def health(container: ContainerDep) -> HealthOut:
    database_ok = True
    try:
        async with container.session_factory() as session:
            await session.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001 - health must never raise
        logger.exception("database health check failed")
        database_ok = False

    workspaces_ok = container.settings.workspaces_dir.is_dir()

    pi_version: str | None = None
    pi_isolated = False
    try:
        info = await probe_pi_runtime(container.settings)
        pi_version = info.version if info.available else None
        pi_isolated = info.source == "managed"
    except Exception:  # noqa: BLE001 - probing must never break health
        logger.warning("pi runtime probe failed", exc_info=True)

    return HealthOut(
        status="ok" if (database_ok and workspaces_ok) else "degraded",
        version=container.settings.app_version,
        database=database_ok,
        workspaces_dir=workspaces_ok,
        coding_agent=container.adapter_name,
        pi_version=pi_version,
        pi_isolated=pi_isolated,
        schema_version=int(container.migration_report.get("to") or 0),
    )
