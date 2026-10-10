"""FastAPI dependencies: container access, database sessions, current user."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from .container import Container
from .models import User

#: Name of the session cookie. HttpOnly + SameSite=Lax; Secure in production.
COOKIE_NAME = "solo_session"


def get_container(request: Request) -> Container:
    """Return the process-wide application container."""
    return request.app.state.container


async def get_session(
    container: Annotated[Container, Depends(get_container)],
) -> AsyncIterator[AsyncSession]:
    """Yield a short-lived database session for read-only handler use."""
    async with container.session_factory() as session:
        yield session


async def get_current_user(
    request: Request,
    container: Annotated[Container, Depends(get_container)],
) -> User:
    """Resolve the authenticated user or raise 401."""
    token = request.cookies.get(COOKIE_NAME)
    user = await container.auth.resolve(token)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="authentication required",
        )
    return user


ContainerDep = Annotated[Container, Depends(get_container)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]
CurrentUser = Annotated[User, Depends(get_current_user)]
