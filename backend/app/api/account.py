"""Account endpoints: view the account, change username, change password.

These exist so a Solo installation can be maintained from the workspace rather
than from the command line — in particular, the password generated at install
time can be replaced after the first sign-in.

Both changes require the current password. A valid session proves the browser
was authenticated at some point; it does not prove the person at the keyboard is
the account owner, and this account can run code and edit files.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request, status

from ..deps import COOKIE_NAME, ContainerDep, CurrentUser
from ..schemas import AccountOut, PasswordUpdate, UsernameUpdate
from ..services.account_service import AccountError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/account", tags=["account"])


def _current_token(request: Request) -> str | None:
    return request.cookies.get(COOKIE_NAME)


def _reject(exc: AccountError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get("", response_model=AccountOut)
async def read_account(
    request: Request, container: ContainerDep, user: CurrentUser
) -> AccountOut:
    try:
        payload = await container.account.describe(
            user.id, current_token=_current_token(request)
        )
    except AccountError as exc:
        raise _reject(exc) from exc
    return AccountOut.model_validate(payload)


@router.put("/username", response_model=AccountOut)
async def change_username(
    payload: UsernameUpdate,
    request: Request,
    container: ContainerDep,
    user: CurrentUser,
) -> AccountOut:
    try:
        await container.account.change_username(
            user.id,
            new_username=payload.new_username,
            current_password=payload.current_password,
        )
        return AccountOut.model_validate(
            await container.account.describe(
                user.id, current_token=_current_token(request)
            )
        )
    except AccountError as exc:
        raise _reject(exc) from exc


@router.put("/password", response_model=AccountOut)
async def change_password(
    payload: PasswordUpdate,
    request: Request,
    container: ContainerDep,
    user: CurrentUser,
) -> AccountOut:
    """Change the password and sign out every other session.

    The browser that makes the change keeps its session, so the user is not
    thrown out of the workspace they are working in.
    """
    try:
        revoked = await container.account.change_password(
            user.id,
            current_password=payload.current_password,
            new_password=payload.new_password,
            current_token=_current_token(request),
        )
    except AccountError as exc:
        raise _reject(exc) from exc

    logger.info("account %s changed its password (%d other session(s) revoked)", user.id, revoked)
    described = await container.account.describe(
        user.id, current_token=_current_token(request)
    )
    described["active_sessions"] = 1
    return AccountOut.model_validate(described)


@router.post("/sessions/revoke", response_model=AccountOut)
async def revoke_other_sessions(
    request: Request, container: ContainerDep, user: CurrentUser
) -> AccountOut:
    """Sign out everywhere else without changing the password."""
    token = _current_token(request)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="no active session cookie was found",
        )
    await container.account.revoke_other_sessions(user.id, token)
    described = await container.account.describe(user.id, current_token=token)
    described["active_sessions"] = 1
    return AccountOut.model_validate(described)
