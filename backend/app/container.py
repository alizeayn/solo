"""Application container: builds and owns long-lived dependencies.

Constructing the container is the only place where concrete implementations are
chosen. Routers and services depend on interfaces, and tests can build a
container against a temporary data directory without touching global state.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from .adapters import build_adapter, resolve_backend
from .adapters.base import CodingAgentAdapter
from .config import Settings
from .db import create_engine, create_session_factory
from .migrations import migrate
from .security import SecretCipher
from .services.account_service import AccountService
from .services.auth_service import AuthService
from .services.checks import ChecksService
from .services.event_bus import EventBus
from .services.narration import NarrationService
from .services.orchestrator import OrchestratorService
from .services.orchestrator_brain import OrchestratorBrain
from .services.pi_config import PiConfigService
from .services.pi_runtime import PiRuntime
from .services.project_service import ProjectService
from .services.project_store import ProjectStoreService
from .services.settings_service import SettingsService

logger = logging.getLogger(__name__)


@dataclass
class Container:
    settings: Settings
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    cipher: SecretCipher
    bus: EventBus
    adapter: CodingAgentAdapter
    auth: AuthService
    account: AccountService
    settings_service: SettingsService
    store: ProjectStoreService
    projects: ProjectService
    pi_config: PiConfigService
    pi_runtime: PiRuntime
    checks: ChecksService
    brain: OrchestratorBrain
    narration: NarrationService
    orchestrator: OrchestratorService
    backend_name: str
    #: Result of the schema migration performed at startup.
    migration_report: dict = field(default_factory=dict)

    @classmethod
    async def create(cls, settings: Settings) -> "Container":
        settings.ensure_directories()
        engine = create_engine(settings.db_path)
        # Creates missing tables and applies any pending migration, reporting
        # what it did so the updater can surface it.
        report = await migrate(engine)
        if report.get("applied"):
            logger.info("schema migrated to version %s", report["to"])
        session_factory = create_session_factory(engine)
        cipher = SecretCipher(settings.key_path)
        bus = EventBus()

        settings_service = SettingsService(session_factory, cipher, settings)
        store = ProjectStoreService(session_factory, settings)
        # One runtime object owns Solo's isolated Pi installation and is shared by
        # the configuration service and the coding-agent adapter.
        pi_runtime = PiRuntime(settings)
        pi_config = PiConfigService(settings, runtime=pi_runtime)
        checks = ChecksService(settings)
        brain = OrchestratorBrain(
            settings=settings, settings_service=settings_service
        )
        # Voice-native output. The default transport records rather than speaks,
        # so the whole narration pipeline (ordering, coalescing, rate limiting,
        # barge-in) is exercised today; Phase 4 attaches audio to it.
        narration = NarrationService(bus=bus)

        # The adapter needs the launch configuration, which lives in settings.
        backend_name = resolve_backend(settings)
        adapter = build_adapter(
            settings,
            backend=backend_name,
            pi_config_loader=settings_service.pi_launch_config,
            pi_runtime=pi_runtime,
        )

        return cls(
            settings=settings,
            engine=engine,
            session_factory=session_factory,
            cipher=cipher,
            bus=bus,
            adapter=adapter,
            auth=AuthService(session_factory, settings),
            account=AccountService(session_factory),
            settings_service=settings_service,
            store=store,
            projects=ProjectService(session_factory, settings, store),
            pi_config=pi_config,
            pi_runtime=pi_runtime,
            checks=checks,
            brain=brain,
            narration=narration,
            orchestrator=OrchestratorService(
                session_factory=session_factory,
                bus=bus,
                adapter=adapter,
                settings=settings,
                store=store,
                brain=brain,
            narration=narration,
                checks=checks,
            ),
            backend_name=backend_name,
            migration_report=report,
        )

    async def close(self) -> None:
        await self.orchestrator.shutdown()
        await self.narration.stop()
        await self.engine.dispose()

    @property
    def adapter_name(self) -> str:
        """Name of the active coding-agent backend (e.g. ``pi`` or ``mock``)."""
        return self.adapter.name
