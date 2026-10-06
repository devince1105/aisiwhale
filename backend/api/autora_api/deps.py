from __future__ import annotations

import secrets
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from autora.accounts import Reader, email_verified, reader_for
from autora.accounts.google import GoogleOAuth
from autora.app import Runtime, build_runtime
from autora.db.session import get_sessionmaker
from autora.infra.email import Sender, build_sender
from autora.infra.settings import Settings, get_settings
from autora.runtime.actor import Actor

_bearer = HTTPBearer(auto_error=False)


def settings_dep() -> Settings:
    return get_settings()


@lru_cache(maxsize=1)
def sender_dep() -> Sender:
    """One email sender per process. Tests override it with one that keeps what it sent."""
    return build_sender(get_settings())


@lru_cache(maxsize=1)
def _google(client_id: str, client_secret: str, redirect_uri: str) -> GoogleOAuth:
    return GoogleOAuth(client_id, client_secret, redirect_uri)


def google_dep() -> GoogleOAuth | None:
    """Google sign-in (D-230), or None when no OAuth client is configured. One per process, so
    Google's signing keys are fetched once an hour, not once a sign-in. Tests override it with
    the same class talking to a stand-in for Google."""
    settings = get_settings()
    if not settings.google_client_id or settings.google_client_secret is None:
        return None
    return _google(
        settings.google_client_id,
        settings.google_client_secret.get_secret_value(),
        settings.google_redirect_uri,
    )


def client_ip(request: Request) -> str:
    """Who is calling, as far as rate limits go (D-230).

    Every public way to the API — api.aisiwhale.com and Render's own onrender.com address — goes
    through Cloudflare, which sets ``CF-Connecting-IP`` to the address that connected to it,
    replacing whatever the client sent. X-Forwarded-For is not used: its first entry is the
    client's to write, and that is the one uvicorn's ``--forwarded-allow-ips '*'`` hands over as
    ``request.client``. Without Cloudflare (dev, tests) the socket's address is all there is."""
    connecting = request.headers.get("cf-connecting-ip", "").strip()
    if connecting:
        return connecting
    return request.client.host if request.client else "unknown"


@lru_cache(maxsize=1)
def runtime_dep() -> Runtime:
    """One wired runtime per process (task manager, workflow engine, approvals, policy)."""
    return build_runtime(get_settings())


async def get_session() -> AsyncIterator[AsyncSession]:
    """One session per request. Handlers commit explicitly; anything uncommitted rolls back."""
    async with get_sessionmaker()() as session:
        yield session


ADMIN_COOKIE = "autora_admin"
"""The back office's own cookie (D-055): apart from a reader's, so signing out of the site does
not sign an admin out of /admin, and a reader's cookie never opens it."""
ADMIN_SESSION_VALID_FOR = timedelta(days=14)
"""Shorter than a reader's 60 days: this one can spend the company's money."""


async def is_admin(session: AsyncSession, reader: Reader, settings: Settings) -> bool:
    """Authorization, apart from how they signed in (D-230): an address on ADMIN_EMAILS **and**
    proven to be theirs. Knowing an admin's address — even registering it — opens nothing."""
    return reader.email in settings.admin_emails and await email_verified(session, reader)


async def admin_for(session: AsyncSession, token: str | None, settings: Settings) -> Reader | None:
    """The admin holding this cookie: a live session, for a proven address still on
    ADMIN_EMAILS."""
    reader = await reader_for(session, token)
    if reader is None or not await is_admin(session, reader, settings):
        return None
    return reader


def admin_actor(reader: Reader) -> Actor:
    """How the company records an admin: by reader id, never by address (D-024)."""
    return Actor.human(f"admin:{reader.id}")


class OfficeCall:
    """When a person last changed something in the back office (D-205).

    Off its shifts the worker asks for this once a minute and comes in when it is new. It lives
    in this process's memory, not the database: answering must not wake the database the shifts
    let sleep. A restart forgets it, and the next shift does the work instead."""

    at: datetime | None = None

    def mark(self) -> None:
        self.at = datetime.now(UTC)


OFFICE_CALL = OfficeCall()
READ_ONLY = frozenset({"GET", "HEAD", "OPTIONS"})


async def require_operator(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    settings: Annotated[Settings, Depends(settings_dep)],
    session: Annotated[AsyncSession, Depends(get_session)],
    autora_admin: Annotated[str | None, Cookie()] = None,
) -> Actor:
    """The back office's caller: the API_BEARER_TOKEN (scripts, CI, server to server), or an
    admin signed in to the back office (D-055, D-230).

    One who changes something calls the worker in, if it is off its shifts (D-205): an approval,
    a draft sent back, a brief, a project resumed. Reading calls nobody."""
    expected = settings.api_bearer_token.get_secret_value()
    actor: Actor | None = None
    if credentials is not None and secrets.compare_digest(credentials.credentials, expected):
        actor = Actor.human("operator")
    else:
        reader = await admin_for(session, autora_admin, settings)
        if reader is not None:
            actor = admin_actor(reader)
    if actor is not None:
        if request.method not in READ_ONLY:
            OFFICE_CALL.mark()
        return actor
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="sign in to the back office, or send the operator token",
        headers={"WWW-Authenticate": "Bearer"},
    )


Session = Annotated[AsyncSession, Depends(get_session)]
EmailSender = Annotated[Sender, Depends(sender_dep)]
Operator = Annotated[Actor, Depends(require_operator)]
Google = Annotated[GoogleOAuth | None, Depends(google_dep)]
ClientIp = Annotated[str, Depends(client_ip)]
RuntimeDep = Annotated[Runtime, Depends(runtime_dep)]
