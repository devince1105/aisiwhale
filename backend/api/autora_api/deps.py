from __future__ import annotations

import logging
import secrets
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession, async_sessionmaker

from autora.accounts import Reader, email_verified, reader_for
from autora.accounts.entitlement import admin_authorized
from autora.accounts.google import GoogleOAuth
from autora.app import Runtime, build_runtime
from autora.db.models import AdminRole, AdminRoleName, OfficeCallRecord
from autora.db.session import get_sessionmaker
from autora.infra.email import Sender, build_sender
from autora.infra.settings import Settings, get_settings
from autora.runtime.actor import Actor
from autora_api import audit, permissions

log = logging.getLogger(__name__)
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


async def role_of(session: AsyncSession, reader: Reader, settings: Settings) -> str | None:
    """A person's back-office role (AD-09): owner for an address on ADMIN_EMAILS, else the role
    an owner gave them, else none. Either way only for an address proven to be theirs."""
    if await admin_authorized(session, reader, settings.admin_emails):
        return AdminRoleName.OWNER.value
    given = await session.get(AdminRole, reader.id)
    if given is None or not await email_verified(session, reader):
        return None
    return given.role


async def is_admin(session: AsyncSession, reader: Reader, settings: Settings) -> bool:
    """Authorization, apart from how they signed in (D-230): an address on ADMIN_EMAILS, or one
    an owner let in (AD-09), **and** proven to be theirs. Knowing an admin's address — even
    registering it — opens nothing."""
    return await role_of(session, reader, settings) is not None


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

    Off its shifts the worker asks for this once a minute and comes in when it is new. It is
    answered from this process's memory, not the database: answering must not wake the database
    the shifts let sleep. It is also written down (D-237) — when a person acts, the database is
    awake anyway — and read back when the API starts, right after the deploy's migrations woke
    it, so a deploy does not forget a call."""

    at: datetime | None = None

    def mark(self) -> None:
        self.at = datetime.now(UTC)

    async def keep(self, bind: AsyncEngine | AsyncConnection) -> None:
        """Write the call down in a transaction of its own, so no request holds the one row while
        it works. A failure is logged: the memory still has the call."""
        if self.at is None:
            return
        statement = insert(OfficeCallRecord).values(id=1, called_at=self.at)
        later = func.greatest(OfficeCallRecord.called_at, statement.excluded.called_at)
        try:
            async with AsyncSession(bind=bind, join_transaction_mode="create_savepoint") as session:
                await session.execute(
                    statement.on_conflict_do_update(
                        index_elements=[OfficeCallRecord.id], set_={"called_at": later}
                    )
                )
                await session.commit()
        except Exception:  # noqa: BLE001 - the call stands without its record
            log.warning("cannot write the call down; only this process remembers it", exc_info=True)

    async def recall(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """At the API's start: the call written down before it, if later than what it has."""
        try:
            async with session_factory() as session:
                called = await session.scalar(select(OfficeCallRecord.called_at))
        except Exception:  # noqa: BLE001 - a start without it is a start as before D-237
            log.warning("cannot read the last call back", exc_info=True)
            return
        if called is not None and (self.at is None or called > self.at):
            self.at = called


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
    a draft sent back, a brief, a project resumed. Reading calls nobody. And what they change is
    written down, who and what (AD-06, audit.py) — refused attempts too.

    What they may do is their role's (AD-09, permissions.py): the token and ADMIN_EMAILS are
    owners; a route that needs a key the role lacks is refused with 403."""
    expected = settings.api_bearer_token.get_secret_value()
    actor: Actor | None = None
    role: str | None = None
    if credentials is not None and secrets.compare_digest(credentials.credentials, expected):
        actor = Actor.human("operator")
        role = AdminRoleName.OWNER.value
    else:
        reader = await admin_for(session, autora_admin, settings)
        if reader is not None:
            actor = admin_actor(reader)
            role = await role_of(session, reader, settings)
    if actor is not None:
        audit.mark(request, actor)
        request.state.admin_role = role
        route = request.scope.get("route")
        key = permissions.needed(request.method, getattr(route, "path", ""))
        if key is not None and key not in permissions.permissions_of(role or ""):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"your role ({role}) does not have {key}",
            )
        if request.method not in READ_ONLY:
            OFFICE_CALL.mark()
            await OFFICE_CALL.keep(session.bind)
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
