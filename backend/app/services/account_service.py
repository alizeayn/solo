"""Account management service: username and password changes.

Both operations require the **current password**, even though the caller already
holds a valid session. A session proves the browser was authenticated at some
point; it does not prove the person at the keyboard is the account owner. That
distinction matters here because the workspace can run code and edit files.

A password change revokes every *other* session, so a change is a reliable way
to end access from another device without signing yourself out.
"""

from __future__ import annotations

import logging
import re

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..models import User
from ..repositories import AuthSessionRepository, UserRepository
from ..security import hash_password, hash_token, verify_password

logger = logging.getLogger(__name__)

MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 256
USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,63}$")


class AccountError(ValueError):
    """A rejected account change, with a message safe to show the user."""


class AccountService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    # ------------------------------------------------------------------ #
    # Read
    # ------------------------------------------------------------------ #
    async def describe(self, user_id: int, *, current_token: str | None = None) -> dict:
        async with self._session_factory() as session:
            user = await UserRepository(session).get(user_id)
            if user is None:
                raise AccountError("account not found")
            sessions = AuthSessionRepository(session)
            active = await sessions.count_for_user(user_id)
        return {
            "username": user.username,
            # A single-user MVP, but the field makes the intent explicit and
            # leaves room for roles later without changing the contract.
            "role": "owner",
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "active_sessions": active,
            "has_session": bool(current_token),
        }

    # ------------------------------------------------------------------ #
    # Change username
    # ------------------------------------------------------------------ #
    async def change_username(
        self, user_id: int, *, new_username: str, current_password: str
    ) -> str:
        username = (new_username or "").strip()
        if not USERNAME_PATTERN.match(username):
            raise AccountError(
                "Use 3–64 characters: letters, digits, dot, dash or underscore, "
                "starting with a letter or digit."
            )

        async with self._session_factory() as session:
            users = UserRepository(session)
            user = await users.get(user_id)
            if user is None:
                raise AccountError("account not found")
            if not verify_password(current_password, user.password_hash):
                raise AccountError("the current password is incorrect")
            if username == user.username:
                return username

            existing = await users.get_by_username(username)
            if existing is not None and existing.id != user_id:
                raise AccountError("that username is already taken")

            user.username = username
            await session.commit()

        logger.info("username changed for account %s", user_id)
        return username

    # ------------------------------------------------------------------ #
    # Change password
    # ------------------------------------------------------------------ #
    async def change_password(
        self,
        user_id: int,
        *,
        current_password: str,
        new_password: str,
        current_token: str | None = None,
    ) -> int:
        """Change the password and revoke every other session.

        Returns the number of sessions revoked.
        """
        if len(new_password or "") < MIN_PASSWORD_LENGTH:
            raise AccountError(
                f"Choose a password of at least {MIN_PASSWORD_LENGTH} characters."
            )
        if len(new_password) > MAX_PASSWORD_LENGTH:
            raise AccountError("That password is too long.")
        if new_password == current_password:
            raise AccountError("The new password must differ from the current one.")

        async with self._session_factory() as session:
            users = UserRepository(session)
            user = await users.get(user_id)
            if user is None:
                raise AccountError("account not found")
            if not verify_password(current_password, user.password_hash):
                raise AccountError("the current password is incorrect")

            user.password_hash = hash_password(new_password)
            keep = hash_token(current_token) if current_token else None
            revoked = await AuthSessionRepository(session).delete_for_user(
                user_id, except_token_hash=keep
            )
            await session.commit()

        logger.info("password changed for account %s; %d session(s) revoked", user_id, revoked)
        return revoked

    # ------------------------------------------------------------------ #
    # Revoke sessions
    # ------------------------------------------------------------------ #
    async def revoke_other_sessions(self, user_id: int, current_token: str) -> int:
        async with self._session_factory() as session:
            revoked = await AuthSessionRepository(session).delete_for_user(
                user_id, except_token_hash=hash_token(current_token)
            )
            await session.commit()
        return revoked
