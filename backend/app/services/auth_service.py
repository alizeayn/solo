"""Authentication service: first-run setup, login, session resolution."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..config import Settings
from ..models import User
from ..repositories import AuthSessionRepository, UserRepository
from ..security import hash_password, hash_token, new_session_token, verify_password

logger = logging.getLogger(__name__)


class AuthService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        settings: Settings,
    ) -> None:
        self._session_factory = session_factory
        self._settings = settings

    # ------------------------------------------------------------------ #
    # Bootstrap
    # ------------------------------------------------------------------ #
    async def is_initialized(self) -> bool:
        async with self._session_factory() as session:
            return await UserRepository(session).count() > 0

    async def bootstrap_admin(self) -> str | None:
        """Create the first admin from the configured bootstrap password.

        The password may come from ``APP_ADMIN_PASSWORD`` or from the
        ``initial-admin-password`` file written by ``install.sh``. The file is
        deleted after use so the plaintext is not retained.

        Returns the username if an account was created, else ``None``.
        """
        async with self._session_factory() as session:
            users = UserRepository(session)
            if await users.count() > 0:
                return None

        password = self._settings.admin_password
        source = "environment"
        # ``is_file`` (not ``exists``) so a Docker-created empty directory at the
        # mount path is ignored rather than raising.
        if not password and self._settings.bootstrap_password_file.is_file():
            try:
                password = self._settings.bootstrap_password_file.read_text().strip()
                source = str(self._settings.bootstrap_password_file)
            except OSError:  # pragma: no cover - unreadable file
                logger.warning("could not read bootstrap password file")
        if not password:
            return None

        async with self._session_factory() as session:
            users = UserRepository(session)
            if await users.count() > 0:
                return None
            await users.create("admin", hash_password(password))
            await session.commit()

        if source != "environment":
            try:
                self._settings.bootstrap_password_file.unlink()
            except OSError:  # pragma: no cover
                pass
        logger.info("created initial admin account from %s", source)
        return "admin"

    # ------------------------------------------------------------------ #
    # Setup / login / logout
    # ------------------------------------------------------------------ #
    async def setup(self, username: str, password: str) -> str | None:
        """Create the first admin account. Returns a session token, or ``None``
        if an account already exists."""
        async with self._session_factory() as session:
            users = UserRepository(session)
            if await users.count() > 0:
                return None
            user = await users.create(username, hash_password(password))
            token = await self._issue_token(session, user)
            await session.commit()
            return token

    async def login(self, username: str, password: str) -> str | None:
        async with self._session_factory() as session:
            user = await UserRepository(session).get_by_username(username)
            if user is None or not verify_password(password, user.password_hash):
                return None
            token = await self._issue_token(session, user)
            await session.commit()
            return token

    async def logout(self, token: str) -> None:
        async with self._session_factory() as session:
            await AuthSessionRepository(session).delete(hash_token(token))
            await session.commit()

    async def resolve(self, token: str | None) -> User | None:
        """Resolve a raw session token to its user, or ``None``."""
        if not token:
            return None
        async with self._session_factory() as session:
            record = await AuthSessionRepository(session).get_valid(hash_token(token))
            if record is None:
                return None
            return record.user

    async def purge_expired_sessions(self) -> None:
        async with self._session_factory() as session:
            await AuthSessionRepository(session).delete_expired()
            await session.commit()

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    async def _issue_token(self, session: AsyncSession, user: User) -> str:
        raw, token_hash = new_session_token()
        expires_at = datetime.now(timezone.utc) + timedelta(
            hours=self._settings.session_ttl_hours
        )
        await AuthSessionRepository(session).create(token_hash, user.id, expires_at)
        return raw
