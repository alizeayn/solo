"""Application container: builds and owns long-lived dependencies.

Constructing the container is the only place where concrete implementations are
chosen. Routers and services depend on interfaces, and tests can build a
container against a temporary data directory without touching global state.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from .adapters import build_adapter, resolve_backend
from .adapters.base import CodingAgentAdapter
from .config import Settings
from .db import create_engine, create_session_factory, init_models
from .security import SecretCipher
from .services.auth_service import AuthService
from .services.checks import ChecksService
from .services.event_bus import EventBus
from .services.orchestrator import OrchestratorService
from .services.orchestrator_brain import OrchestratorBrain
from .services.pi_config import PiConfigService
from .services.project_service import ProjectService
from .services.project_store import ProjectStoreService
from .services.settings_service import SettingsService


@dataclass
class Container:
    settings: Settings
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    cipher: SecretCipher
    bus: EventBus
    adapter: CodingAgentAdapter
    auth: AuthService
    settings_service: SettingsService
    store: ProjectStoreService
    projects: ProjectService
    pi_config: PiConfigService
    checks: ChecksService
    brain: OrchestratorBrain
    orchestrator: OrchestratorService
    backend_name: str

    @classmethod
    async def create(cls, settings: Settings) -> "Container":
        settings.ensure_directories()
        engine = create_engine(settings.db_path)
        await init_models(engine)
        session_factory = create_session_factory(engine)
        cipher = SecretCipher(settings.key_path)
        bus = EventBus()

        settings_service = SettingsService(session_factory, cipher, settings)
        store = ProjectStoreService(session_factory, settings)
        pi_config = PiConfigService(settings)
        checks = ChecksService(settings)
        brain = OrchestratorBrain(
            settings=settings, settings_service=settings_service
        )

        # The adapter needs the launch configuration, which lives in settings.
        backend_name = resolve_backend(settings)
        adapter = build_adapter(
            settings,
            backend=backend_name,
            pi_config_loader=settings_service.pi_launch_config,
        )

        return cls(
            settings=settings,
            engine=engine,
            session_factory=session_factory,
            cipher=cipher,
            bus=bus,
            adapter=adapter,
            auth=AuthService(session_factory, settings),
            settings_service=settings_service,
            store=store,
            projects=ProjectService(session_factory, settings, store),
            pi_config=pi_config,
            checks=checks,
            brain=brain,
            orchestrator=OrchestratorService(
                session_factory=session_factory,
                bus=bus,
                adapter=adapter,
                settings=settings,
                store=store,
                brain=brain,
                checks=checks,
            ),
            backend_name=backend_name,
        )

    async def close(self) -> None:
        await self.orchestrator.shutdown()
        await self.engine.dispose()

    @property
    def adapter_name(self) -> str:
        """Name of the active coding-agent backend (e.g. ``pi`` or ``mock``)."""
        return self.adapter.name
