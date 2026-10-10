"""Authentication endpoints: first-run setup, login, logout, session status."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response, status

from ..deps import COOKIE_NAME, ContainerDep, CurrentUser
from ..schemas import AuthStatus, LoginRequest, SetupRequest

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _set_session_cookie(response: Response, token: str, container: ContainerDep) -> None:
    settings = container.settings
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        secure=settings.is_production,
        max_age=settings.session_ttl_hours * 3600,
        path="/",
    )


def _clear_session_cookie(response: Response) -> None:
    response.delete_cookie(key=COOKIE_NAME, path="/")


@router.get("/status", response_model=AuthStatus)
async def auth_status(request: Request, container: ContainerDep) -> AuthStatus:
    """Public endpoint: tells the UI whether setup is needed and if we're signed in."""
    initialized = await container.auth.is_initialized()
    user = await container.auth.resolve(request.cookies.get(COOKIE_NAME))
    return AuthStatus(
        initialized=initialized,
        authenticated=user is not None,
        username=user.username if user else None,
    )


@router.post("/setup", response_model=AuthStatus, status_code=status.HTTP_201_CREATED)
async def setup(
    payload: SetupRequest, response: Response, container: ContainerDep
) -> AuthStatus:
    """Create the first (and only) admin account. Disabled once initialized."""
    token = await container.auth.setup(payload.username, payload.password)
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="application is already initialized",
        )
    _set_session_cookie(response, token, container)
    return AuthStatus(initialized=True, authenticated=True, username=payload.username)


@router.post("/login", response_model=AuthStatus)
async def login(
    payload: LoginRequest, response: Response, container: ContainerDep
) -> AuthStatus:
    token = await container.auth.login(payload.username, payload.password)
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid username or password",
        )
    _set_session_cookie(response, token, container)
    return AuthStatus(initialized=True, authenticated=True, username=payload.username)


@router.post("/logout", response_model=AuthStatus)
async def logout(
    request: Request, response: Response, container: ContainerDep
) -> AuthStatus:
    token = request.cookies.get(COOKIE_NAME)
    if token:
        await container.auth.logout(token)
    _clear_session_cookie(response)
    return AuthStatus(
        initialized=await container.auth.is_initialized(),
        authenticated=False,
        username=None,
    )


@router.get("/me", response_model=AuthStatus)
async def me(user: CurrentUser, container: ContainerDep) -> AuthStatus:
    return AuthStatus(initialized=True, authenticated=True, username=user.username)
