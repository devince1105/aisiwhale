"""Signing in to the back office (D-055, D-230): the readers' own sign-in, through its own door.

- POST /api/admin/auth/login         {email, password} -> who signed in, and the admin cookie
- GET  /api/admin/auth/google/start  ?next -> 303 to Google; back through the shared callback
- GET  /api/admin/auth/me            -> who is calling the back office, or 401
- POST /api/admin/auth/logout        -> 204, the session revoked and the cookie cleared

There is no separate admin account: an admin is a reader who signed in — with their password or
with Google — and whom the back office lets in (authorization, apart from authentication):
an address on ADMIN_EMAILS **and** proven to be theirs (``deps.is_admin``). The session lasts 14
days, not 60, and lives in its own cookie. Being let in is checked again on every request
(``deps.require_operator``), not only here.
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Cookie, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field

from autora.accounts import OAuthPurpose, authenticate, ratelimit, sign_out, start_session
from autora.infra.settings import Settings
from autora_api.deps import (
    ADMIN_COOKIE,
    ADMIN_SESSION_VALID_FOR,
    ClientIp,
    Google,
    Session,
    admin_for,
    is_admin,
    require_operator,
    settings_dep,
)
from autora_api.routers.auth import WRONG, begin_google, limit, set_admin_cookie

router = APIRouter(prefix="/api/admin/auth", tags=["admin-auth"])

SettingsDep = Annotated[Settings, Depends(settings_dep)]
AdminCookie = Annotated[str | None, Cookie(alias=ADMIN_COOKIE)]
ADMIN_NEXT = r"^/admin(/[^\s]*)?$"
"""Where to go after signing in: a page of the back office, never another address."""


class Login(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(min_length=1, max_length=1024)


class AdminMe(BaseModel):
    via: Literal["email", "token"]
    email: str | None
    """The admin's address, to show them who they are signed in as; None with the token."""


@router.post("/login")
async def login(
    body: Login, session: Session, settings: SettingsDep, response: Response, ip: ClientIp
) -> AdminMe:
    await limit(session, ratelimit.LOGIN, ip, body.email)
    reader = await authenticate(session, body.email, body.password)
    if reader is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, WRONG)
    if not await is_admin(session, reader, settings):
        await session.commit()  # a rehashed password, if any
        raise HTTPException(status.HTTP_403_FORBIDDEN, "this account may not open the back office")
    token = await start_session(session, reader, valid_for=ADMIN_SESSION_VALID_FOR)
    await session.commit()
    set_admin_cookie(response, token, settings)
    return AdminMe(via="email", email=reader.email)


@router.get("/google/start")
async def google_start(
    session: Session,
    settings: SettingsDep,
    google: Google,
    ip: ClientIp,
    next: Annotated[str | None, Query(max_length=200, pattern=ADMIN_NEXT)] = None,  # noqa: A002
) -> Response:
    await limit(session, ratelimit.GOOGLE_START, ip)
    return await begin_google(
        session, google, settings, OAuthPurpose.ADMIN, lang="zh-TW", next_path=next
    )


@router.get("/me", dependencies=[Depends(require_operator)])
async def me(
    session: Session,
    settings: SettingsDep,
    autora_admin: AdminCookie = None,
) -> AdminMe:
    """Who is calling. ``require_operator`` has already refused anybody else."""
    reader = await admin_for(session, autora_admin, settings)
    await session.commit()  # last_seen_at
    if reader is not None:
        return AdminMe(via="email", email=reader.email)
    return AdminMe(via="token", email=None)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    session: Session, settings: SettingsDep, autora_admin: AdminCookie = None
) -> Response:
    await sign_out(session, autora_admin)
    await session.commit()
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.delete_cookie(ADMIN_COOKIE, path="/", domain=settings.cookie_domain or None)
    return response
