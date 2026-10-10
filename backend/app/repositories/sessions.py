"""Authentication-session repository (opaque server-side sessions)."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..models import AuthSession


class AuthSessionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self, token_hash: str, user_id: int, expires_at: datetime
    ) -> AuthSession:
        record = AuthSession(
            token_hash=token_hash, user_id=user_id, expires_at=expires_at
        )
        self.session.add(record)
        await self.session.flush()
        return record

    async def get_valid(self, token_hash: str) -> AuthSession | None:
        """Return a non-expired session (with eager-loaded user) or ``None``."""
        result = await self.session.execute(
            select(AuthSession)
            .options(selectinload(AuthSession.user))
            .where(AuthSession.token_hash == token_hash)
        )
        record = result.scalar_one_or_none()
        if record is None:
            return None
        expires = record.expires_at
        # SQLite may return naive datetimes; normalise before comparing.
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if expires <= datetime.now(timezone.utc):
            return None
        return record

    async def delete(self, token_hash: str) -> None:
        await self.session.execute(
            delete(AuthSession).where(AuthSession.token_hash == token_hash)
        )

    async def delete_expired(self) -> None:
        await self.session.execute(
            delete(AuthSession).where(
                AuthSession.expires_at <= datetime.now(timezone.utc)
            )
        )
