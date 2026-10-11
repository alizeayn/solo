"""FastAPI application factory.

Single user-facing origin: the REST API, the WebSocket and (in production) the
built frontend are all served by this one app.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .api import account as account_api
from .api import auth as auth_api
from .api import files as files_api
from .api import fs as fs_api
from .api import health as health_api
from .api import messages as messages_api
from .api import milestones as milestones_api
from .api import orchestration as orchestration_api
from .api import orchestrator as orchestrator_api
from .api import pi as pi_api
from .api import projects as projects_api
from .api import settings as settings_api
from .api import tasks as tasks_api
from .api import voice as voice_api
from .api import ws as ws_api
from .config import Settings, get_settings
from .container import Container
from .logging_setup import configure_logging

logger = logging.getLogger(__name__)

_STATE_CHANGING = {"POST", "PUT", "PATCH", "DELETE"}


def _install_middleware(app: FastAPI, settings: Settings) -> None:
    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        # CSRF defence-in-depth: the session cookie is SameSite=Lax, and we
        # additionally reject state-changing requests whose Origin does not
        # match this host. Requests without an Origin (curl, tests) are allowed.
        if request.method in _STATE_CHANGING:
            origin = request.headers.get("origin")
            if origin:
                parsed = urlparse(origin)
                if parsed.netloc and parsed.netloc != request.headers.get("host", ""):
                    return JSONResponse(
                        {"detail": "cross-origin request rejected"}, status_code=403
                    )

        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        return response


def _mount_frontend(app: FastAPI, settings: Settings) -> None:
    if settings.frontend_dist and Path(settings.frontend_dist).is_dir():
        app.mount(
            "/",
            StaticFiles(directory=str(settings.frontend_dist), html=True),
            name="frontend",
        )
        return

    @app.get("/", include_in_schema=False)
    async def dev_root() -> dict[str, str]:
        return {
            "name": "Solo API",
            "version": __version__,
            "docs": "/api/docs",
            "note": "Frontend is served by Vite in development.",
        }


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the FastAPI application."""
    settings = settings or get_settings()
    configure_logging(settings.log_level)
    settings.ensure_directories()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        container = await Container.create(settings)
        app.state.container = container
        # Create Solo's own Pi runtime and agent directories up front, so the
        # Settings UI can report a truthful status on first load.
        try:
            container.pi_runtime.initialize()
        except OSError:  # pragma: no cover - read-only data dir
            logger.warning("could not create the Pi runtime directories", exc_info=True)
        # Create the first admin from the installer-provided password, if any.
        await container.auth.bootstrap_admin()
        await container.auth.purge_expired_sessions()
        await container.orchestrator.start()
        await container.narration.start()
        logger.info(
            "application ready (agent=%s, data_dir=%s)",
            container.adapter_name,
            settings.app_data_dir,
        )
        try:
            yield
        finally:
            await container.close()

    app = FastAPI(
        title="Solo",
        version=__version__,
        lifespan=lifespan,
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )

    # --- Public routes (no authentication) ---
    app.include_router(health_api.router)
    app.include_router(auth_api.router)
    app.include_router(ws_api.router)

    # --- Authenticated routes (enforced by the CurrentUser dependency) ---
    app.include_router(account_api.router)
    app.include_router(settings_api.router)
    app.include_router(projects_api.router)
    app.include_router(fs_api.router)
    app.include_router(files_api.router)
    app.include_router(tasks_api.router)
    app.include_router(messages_api.router)
    app.include_router(milestones_api.router)
    app.include_router(pi_api.router)
    app.include_router(orchestrator_api.router)
    app.include_router(orchestration_api.router)
    app.include_router(voice_api.router)

    _install_middleware(app, settings)
    _mount_frontend(app, settings)
    return app


app = create_app
