"""Readers signing in, and what the site may know about them (D-025, D-230).

- POST /api/auth/register         {email, password, lang?} -> 202, always
- POST /api/auth/login            {email, password} -> the reader, and a session cookie
- POST /api/auth/logout           -> 204, the session revoked and the cookie cleared
- GET  /api/auth/me               -> who is signed in, and until when they are a member; and,
                                     once a month per tier, their coins (P3-B, when on)
- POST /api/auth/email/verify     {token} -> 204, the address proven
- POST /api/auth/email/resend     {lang?} -> 202, a new link to prove it (signed in)
- POST /api/auth/password/forgot  {email, lang?} -> 202, always
- POST /api/auth/password/reset   {token, password} -> the reader, and a new session cookie
- GET  /api/auth/google/start     ?lang&next -> 303 to Google
- GET  /api/auth/google/callback  ?state&code -> 303 back to the site, signed in or told why not

No bearer token: these belong to the public site. The answer to "who are you" is whatever the
cookie proves and nothing else. Registering and asking for a reset answer the same way for an
address that has an account and one that does not, and a failed sign-in says only that the
address or password is wrong — none of these may become a way to ask who reads here.

Every one of them is rate limited (``accounts.ratelimit``); the count is committed before the
work, so a try that fails is still counted.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Cookie, Depends, HTTPException, Query, Response, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from autora.accounts import (
    SESSION_COOKIE,
    AccountError,
    OAuthPurpose,
    PasswordError,
    Reader,
    authenticate,
    by_email,
    email_verified,
    normalise,
    passwords,
    ratelimit,
    reader_for,
    register,
    request_reset,
    request_verification,
    reset_password,
    service,
    sign_out,
    start_session,
    verify_email,
)
from autora.accounts import emails as reader_emails
from autora.accounts import google as google_signin
from autora.accounts.coins import grant_monthly
from autora.accounts.entitlement import Tier, entitlement_for
from autora.accounts.service import SESSION_VALID_FOR
from autora.db.models import Company
from autora.infra.email import EmailError
from autora.infra.settings import Settings
from autora_api.deps import (
    ADMIN_COOKIE,
    ADMIN_SESSION_VALID_FOR,
    ClientIp,
    EmailSender,
    Google,
    Session,
    is_admin,
    settings_dep,
)

log = logging.getLogger(__name__)

router = APIRouter(tags=["auth"])

ADDRESS = service.ADDRESS_PATTERN
"""The same shape the accounts layer accepts, so the form and the service agree."""
LANG = r"^[a-z]{2}(-[A-Z][A-Za-z]{1,3})?$"
NEXT_PATH = r"^/[^\s]*$"
"""Where to go afterwards: a path inside the site, put after the site's own address."""
PASSWORD = Field(min_length=1, max_length=1024)
"""Only a bound on what is read: the rule for a new password is ``accounts.passwords``'s."""

OAUTH_COOKIE = "autora_oauth"
"""The starting browser's half of a Google sign-in in flight (D-230): only the browser that went
to Google can come back from it. Scoped to the callback's path, for ten minutes."""
OAUTH_COOKIE_PATH = "/api/auth/google"

SessionCookie = Annotated[str | None, Cookie(alias=SESSION_COOKIE)]
SettingsDep = Annotated[Settings, Depends(settings_dep)]
CompanySlug = Annotated[str | None, Query(max_length=100)]

TOO_MANY = "too many tries; wait a while and try again"
WRONG = "the email or the password is wrong"


class Register(BaseModel):
    email: str = Field(max_length=254, pattern=ADDRESS)
    password: str = PASSWORD
    lang: str = Field(default=reader_emails.DEFAULT_LANG, pattern=LANG)
    """Which language's pages the emailed link opens."""


class Login(BaseModel):
    email: str = Field(max_length=254)
    password: str = PASSWORD


class Forgot(BaseModel):
    email: str = Field(max_length=254)
    lang: str = Field(default=reader_emails.DEFAULT_LANG, pattern=LANG)


class Reset(BaseModel):
    token: str = Field(min_length=10, max_length=200)
    password: str = PASSWORD


class Verify(BaseModel):
    token: str = Field(min_length=10, max_length=200)


class Resend(BaseModel):
    lang: str = Field(default=reader_emails.DEFAULT_LANG, pattern=LANG)


class Me(BaseModel):
    reader_id: uuid.UUID
    email: str
    email_verified: bool = False
    """Whether the address is proven (D-230). Until it is, it opens nothing that depends on it."""
    member_until: datetime | None = None
    """When their access runs out. None: they are not a member of this company."""
    tier: Literal["public", "free", "vip"] = "free"
    """Who they are to the site (P2), decided by the server: ``vip`` while a membership of this
    company is running, bought or given (D-228). The browser shows it, never works it out."""
    capabilities: list[str] = []
    """What the tier and being an admin allow (``accounts.entitlement.Capability``)."""

    @property
    def member(self) -> bool:
        return self.member_until is not None


async def company_id_for(session, slug: str | None) -> uuid.UUID | None:
    """The company a reader request is about: ``?company=<slug>``, or the oldest there is.
    ``/me`` and ``/api/me/coins`` both ask it, so their tier is the same."""
    query = select(Company.id) if slug is None else select(Company.id).where(Company.slug == slug)
    return await session.scalar(query.order_by(Company.created_at).limit(1))


async def _me(session, reader, slug: str | None, settings: Settings) -> Me:
    company_id = await company_id_for(session, slug)
    granted = await entitlement_for(
        session, reader, company_id=company_id, admin_emails=settings.admin_emails
    )
    return Me(
        reader_id=reader.id,
        email=reader.email,
        email_verified=await email_verified(session, reader),
        member_until=granted.vip_until,
        tier=granted.tier.value,
        capabilities=sorted(c.value for c in granted.capabilities),
    )


def _secure(settings: Settings) -> bool:
    return settings.site_base_url.startswith("https://")


def _set_cookie(response: Response, token: str, settings: Settings) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=int(SESSION_VALID_FOR.total_seconds()),
        httponly=True,
        samesite="lax",
        secure=_secure(settings),
        path="/",
        domain=settings.cookie_domain or None,
    )


def set_admin_cookie(response: Response, token: str, settings: Settings) -> None:
    """The back office's own cookie (D-055): the same session rows, a shorter life."""
    response.set_cookie(
        ADMIN_COOKIE,
        token,
        max_age=int(ADMIN_SESSION_VALID_FOR.total_seconds()),
        httponly=True,
        samesite="lax",
        secure=_secure(settings),
        path="/",
        domain=settings.cookie_domain or None,
    )


async def limit(
    session: AsyncSession, rule: ratelimit.Limit, ip: str, email: str | None = None
) -> None:
    """Count this try, committed at once; 429 when it is one too many."""
    allowed = await ratelimit.allow(session, rule, ip=ip, email=email)
    await session.commit()
    if not allowed:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, TOO_MANY)


async def _send(sender, message) -> None:
    try:
        await sender.send(message)
    except EmailError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "the email could not be sent") from exc


@router.post("/api/auth/register", status_code=status.HTTP_202_ACCEPTED)
async def register_reader(
    body: Register, session: Session, settings: SettingsDep, sender: EmailSender, ip: ClientIp
) -> Response:
    """Make an account with an unverified address and email a link to prove it. An address that
    already has an account is left as it is and its owner is emailed; the answer is the same.

    An address on ADMIN_EMAILS that has no account yet is not given one here (D-230): somebody
    registering it first, with a password of their own, would hold an account the admin might
    then prove by opening our link. Its owner is emailed the ways in that prove the address
    themselves — Google, or a password reset — and the answer is the same as for anybody."""
    await limit(session, ratelimit.REGISTER, ip, body.email)
    try:
        address = normalise(body.email)
        passwords.check_new(body.password)
    except (AccountError, PasswordError) as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    if address in settings.admin_emails and await by_email(session, address) is None:
        passwords.hash_password(body.password)  # the work a registration does, so it takes as long
        message = reader_emails.registration_closed_email(
            address, settings.site_base_url, lang=body.lang
        )
    else:
        outcome = await register(session, address, body.password)
        to = outcome.reader.email
        if outcome.verify_token is not None:
            url = reader_emails.verify_url(
                settings.site_base_url, outcome.verify_token, lang=body.lang
            )
            message = reader_emails.verify_email(to, url)
        else:
            message = reader_emails.account_exists_email(to, settings.site_base_url, lang=body.lang)
    await _send(sender, message)
    await session.commit()
    return Response(status_code=status.HTTP_202_ACCEPTED)


@router.post("/api/auth/login")
async def login(
    body: Login,
    session: Session,
    settings: SettingsDep,
    response: Response,
    ip: ClientIp,
    company: CompanySlug = None,
) -> Me:
    await limit(session, ratelimit.LOGIN, ip, body.email)
    reader = await authenticate(session, body.email, body.password)
    if reader is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, WRONG)
    token = await start_session(session, reader)
    me = await _me(session, reader, company, settings)
    await session.commit()
    _set_cookie(response, token, settings)
    return me


@router.get("/api/auth/me")
async def me(
    session: Session,
    settings: SettingsDep,
    autora_reader: SessionCookie = None,
    company: CompanySlug = None,
) -> Me | None:
    reader = await reader_for(session, autora_reader)
    if reader is None:
        return None
    answer = await _me(session, reader, company, settings)
    await session.commit()  # last_seen_at
    await _grant_this_month(session, answer)
    return answer


async def _grant_this_month(session: AsyncSession, answer: Me) -> None:
    """The month's coins for the tier just worked out (P3-B, D-235), in a transaction of its own
    after ``/me``'s commit: the ledger's checks run at commit, and nothing about coins may break
    the header. A failure is logged and tried again on the next ``/me``; the key keeps it once."""
    try:
        await grant_monthly(
            session,
            answer.reader_id,
            tier=Tier(answer.tier),
            email_verified=answer.email_verified,
        )
        await session.commit()
    except Exception:
        await session.rollback()
        log.exception("monthly coin grant failed for reader %s", answer.reader_id)


@router.post("/api/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    session: Session,
    response: Response,
    settings: SettingsDep,
    autora_reader: SessionCookie = None,
) -> Response:
    await sign_out(session, autora_reader)
    await session.commit()
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.delete_cookie(SESSION_COOKIE, path="/", domain=settings.cookie_domain or None)
    return response


@router.post("/api/auth/email/verify", status_code=status.HTTP_204_NO_CONTENT)
async def verify_address(body: Verify, session: Session, ip: ClientIp) -> Response:
    """Prove the address the link was sent to. Signs nobody in."""
    await limit(session, ratelimit.VERIFY_EMAIL, ip)
    try:
        await verify_email(session, body.token)
    except AccountError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/api/auth/email/resend", status_code=status.HTTP_202_ACCEPTED)
async def resend_verification(
    body: Resend,
    session: Session,
    settings: SettingsDep,
    sender: EmailSender,
    ip: ClientIp,
    autora_reader: SessionCookie = None,
) -> Response:
    """A new link to prove the signed-in reader's address; nothing when it is already proven."""
    reader = await reader_for(session, autora_reader)
    if reader is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "sign in first")
    await limit(session, ratelimit.RESEND_VERIFICATION, ip, reader.email)
    token = await request_verification(session, reader)
    if token is not None:
        url = reader_emails.verify_url(settings.site_base_url, token, lang=body.lang)
        await _send(sender, reader_emails.verify_email(reader.email, url))
    await session.commit()
    return Response(status_code=status.HTTP_202_ACCEPTED)


@router.post("/api/auth/password/forgot", status_code=status.HTTP_202_ACCEPTED)
async def forgot_password(
    body: Forgot, session: Session, settings: SettingsDep, sender: EmailSender, ip: ClientIp
) -> Response:
    """Email a link to set a new password. 202 whether or not the address has an account."""
    await limit(session, ratelimit.FORGOT_PASSWORD, ip, body.email)
    found = await request_reset(session, body.email)
    if found is not None:
        reader, token = found
        url = reader_emails.reset_url(settings.site_base_url, token, lang=body.lang)
        await _send(sender, reader_emails.reset_email(reader.email, url))
    await session.commit()
    return Response(status_code=status.HTTP_202_ACCEPTED)


@router.post("/api/auth/password/reset")
async def set_password(
    body: Reset,
    session: Session,
    settings: SettingsDep,
    response: Response,
    ip: ClientIp,
    company: CompanySlug = None,
) -> Me:
    """Set the new password; every other session of the reader ends, and this browser gets a
    new one."""
    await limit(session, ratelimit.RESET_PASSWORD, ip)
    try:
        reader = await reset_password(session, body.token, body.password)
    except PasswordError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    except AccountError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    token = await start_session(session, reader)
    me = await _me(session, reader, company, settings)
    await session.commit()
    _set_cookie(response, token, settings)
    return me


# --- Google (D-230) ---


async def begin_google(
    session: AsyncSession,
    google,
    settings: Settings,
    purpose: OAuthPurpose,
    *,
    lang: str,
    next_path: str | None,
) -> Response:
    """Send the browser to Google, keeping this sign-in's browser half in a cookie."""
    if google is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Google sign-in is not set up")
    start = await google_signin.begin(session, google, purpose, lang=lang, next_path=next_path)
    await session.commit()
    response = RedirectResponse(start.url, status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(
        OAUTH_COOKIE,
        start.browser,
        max_age=int(google_signin.STATE_VALID_FOR.total_seconds()),
        httponly=True,
        samesite="lax",  # sent back on Google's top-level redirect to the callback
        secure=_secure(settings),
        path=OAUTH_COOKIE_PATH,
    )
    return response


@router.get("/api/auth/google/start")
async def google_start(
    session: Session,
    settings: SettingsDep,
    google: Google,
    ip: ClientIp,
    lang: Annotated[str, Query(pattern=LANG)] = reader_emails.DEFAULT_LANG,
    next: Annotated[str | None, Query(max_length=200, pattern=NEXT_PATH)] = None,  # noqa: A002
) -> Response:
    await limit(session, ratelimit.GOOGLE_START, ip)
    return await begin_google(
        session, google, settings, OAuthPurpose.READER, lang=lang, next_path=next
    )


def _back(settings: Settings, purpose: str, lang: str, *, error: str | None, next_path: str | None):
    """Where the browser goes when Google is done with it."""
    site = settings.site_base_url.rstrip("/")
    if purpose == OAuthPurpose.ADMIN:
        if error is None:
            return f"{site}{next_path or '/admin/dashboard'}"
        return f"{site}/admin/login?error={error}"
    if error is None:
        return f"{site}{next_path or f'/news/{lang}'}"
    return f"{site}/news/{lang}/login?error={error}"


@router.get("/api/auth/google/callback")
async def google_callback(
    session: Session,
    settings: SettingsDep,
    google: Google,
    ip: ClientIp,
    state: Annotated[str | None, Query(max_length=200)] = None,
    code: Annotated[str | None, Query(max_length=2000)] = None,
    error: Annotated[str | None, Query(max_length=200)] = None,
    autora_oauth: Annotated[str | None, Cookie()] = None,
) -> Response:
    """Finish a Google sign-in: claim its state, trade the code, check the token, find the
    reader, sign them in. Every failure goes back to the login page with a reason code."""
    await limit(session, ratelimit.GOOGLE_CALLBACK, ip)
    if google is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Google sign-in is not set up")
    purpose, lang, next_path = OAuthPurpose.READER.value, reader_emails.DEFAULT_LANG, None
    reader: Reader | None = None
    failure: str | None = None
    try:
        flight = await google_signin.claim(session, state, autora_oauth)
        purpose, lang, next_path = flight.purpose, flight.lang, flight.next_path
        await session.commit()  # the state is spent, whatever happens next
        if error is not None or not code:
            failure = "google_cancelled"
        else:
            id_token = await google.exchange(code, flight.code_verifier)
            account = await google.verify(id_token, nonce=flight.nonce)
            reader = await google_signin.sign_in(session, account)
    except google_signin.GoogleError:
        failure = "google_failed"
    except google_signin.SignInRefused as refused:
        failure = refused.reason
    if reader is not None and purpose == OAuthPurpose.ADMIN:
        if not await is_admin(session, reader, settings):
            await session.rollback()  # the back office's door makes no reader, links nothing
            failure, reader = "not_admin", None
    target = _back(settings, purpose, lang, error=failure, next_path=next_path)
    response = RedirectResponse(target, status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(OAUTH_COOKIE, path=OAUTH_COOKIE_PATH)
    if reader is None:
        await session.commit()
        return response
    if purpose == OAuthPurpose.ADMIN:
        token = await start_session(session, reader, valid_for=ADMIN_SESSION_VALID_FOR)
        await session.commit()
        set_admin_cookie(response, token, settings)
    else:
        token = await start_session(session, reader)
        await session.commit()
        _set_cookie(response, token, settings)
    return response
