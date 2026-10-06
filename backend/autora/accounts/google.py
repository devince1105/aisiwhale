"""Signing in with Google: OAuth 2.0's authorization code flow, with PKCE (D-230).

The browser is sent to Google with a ``state`` and a PKCE challenge, and comes back with a code.
The API — never the browser — trades the code (and the PKCE verifier only it knows) for an ID
token, and believes nothing in it until the token is checked: signed by one of Google's
published keys, issued by Google, made for this app (``aud``), not expired, and carrying the
``nonce`` this attempt sent. Nothing about who somebody is is ever taken from the browser.

A sign-in in flight is an ``oauth_states`` row: used once, for ten minutes, and only from the
browser that started it (a nonce in that browser's cookie, its hash in the row), so somebody
cannot start a sign-in to their own account and finish it in somebody else's browser.

Who the Google account is, here (``sign_in``):

- **Its ``sub`` is already linked** — that reader. Whatever the account's address is now.
- **Google says the address is not verified** — refused: an unproven address is never matched.
- **No reader has the address** — a new reader, with this Google account.
- **A reader has the address** — linked to it only if that reader's address is proven (a link we
  sent was opened, or a reset done). An unproven address may have been registered by somebody
  else, waiting for its owner to arrive: refused, and its owner can prove the address (reset
  the password) and then sign in with Google. Nothing of the reader's is changed or removed.

Only the exact address counts: never a name, a picture, a domain or a near match.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

import httpx
import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from autora.accounts.credentials import identity
from autora.accounts.models import OAuthPurpose, OAuthState, Provider, Reader, ReaderIdentity
from autora.accounts.service import AccountError, by_email, hash_token

AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
CERTS_URL = "https://www.googleapis.com/oauth2/v3/certs"
ISSUERS = ("https://accounts.google.com", "accounts.google.com")
STATE_VALID_FOR = timedelta(minutes=10)
KEYS_KEPT_FOR = 3600.0
"""Google rotates its signing keys every few days; an hour's copy, refetched for an unknown kid."""
LEEWAY_SECONDS = 30
"""Clock difference allowed when checking ``exp`` and ``iat``."""


class GoogleError(Exception):
    """The sign-in did not come back as it should: a bad state, code or token. Said to the
    reader as one thing — "Google sign-in failed" — whichever it was."""


class SignInRefused(Exception):
    """A real Google account that may not sign in here as things are. ``reason`` is shown."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


EMAIL_NOT_VERIFIED = "google_email_unverified"
ADDRESS_NOT_PROVEN = "google_needs_verified_email"
ANOTHER_GOOGLE_LINKED = "google_other_account_linked"


@dataclass(frozen=True)
class GoogleAccount:
    """What a checked ID token says. ``email`` lowercased; nothing else is kept."""

    sub: str
    email: str
    email_verified: bool


@dataclass(frozen=True)
class Start:
    """A sign-in about to leave for Google. ``browser`` goes in the starting browser's cookie."""

    url: str
    browser: str


def _challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


class GoogleOAuth:
    """Google's side of the flow. ``http`` is the client its requests go through."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        *,
        http: httpx.AsyncClient | None = None,
    ) -> None:
        self.client_id = client_id
        self._secret = client_secret
        self.redirect_uri = redirect_uri
        self._http = http or httpx.AsyncClient(timeout=10.0)
        self._keys: dict[str, Any] = {}
        self._keys_at = 0.0

    def authorization_url(self, *, state: str, verifier: str, nonce: str) -> str:
        query = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": "openid email",
            "state": state,
            "nonce": nonce,
            "code_challenge": _challenge(verifier),
            "code_challenge_method": "S256",
            "prompt": "select_account",
        }
        return f"{AUTHORIZE_URL}?{urlencode(query)}"

    async def exchange(self, code: str, verifier: str) -> str:
        """The ID token for this code. Raises GoogleError when Google will not give one."""
        try:
            response = await self._http.post(
                TOKEN_URL,
                data={
                    "code": code,
                    "client_id": self.client_id,
                    "client_secret": self._secret,
                    "redirect_uri": self.redirect_uri,
                    "grant_type": "authorization_code",
                    "code_verifier": verifier,
                },
            )
        except httpx.HTTPError as exc:
            raise GoogleError("Google could not be reached") from exc
        if response.status_code != 200:
            raise GoogleError(f"Google refused the code ({response.status_code})")
        token = response.json().get("id_token")
        if not isinstance(token, str) or not token:
            raise GoogleError("Google answered without an ID token")
        return token

    async def _key(self, kid: str) -> Any:
        stale = time.monotonic() - self._keys_at > KEYS_KEPT_FOR
        if stale or kid not in self._keys:
            try:
                response = await self._http.get(CERTS_URL)
                response.raise_for_status()
                keys = response.json()["keys"]
            except (httpx.HTTPError, KeyError, ValueError) as exc:
                raise GoogleError("Google's signing keys could not be read") from exc
            self._keys = {key["kid"]: jwt.PyJWK(key).key for key in keys if "kid" in key}
            self._keys_at = time.monotonic()
        if kid not in self._keys:
            raise GoogleError("the ID token was signed with a key Google does not publish")
        return self._keys[kid]

    async def verify(self, id_token: str, *, nonce: str) -> GoogleAccount:
        """What the ID token says, once it is proven to be Google's, for this app and attempt."""
        try:
            header = jwt.get_unverified_header(id_token)
        except jwt.PyJWTError as exc:
            raise GoogleError("the ID token is not a token") from exc
        if header.get("alg") != "RS256" or not isinstance(header.get("kid"), str):
            raise GoogleError("the ID token is not signed the way Google signs")
        key = await self._key(header["kid"])
        try:
            claims = jwt.decode(
                id_token,
                key,
                algorithms=["RS256"],
                audience=self.client_id,
                leeway=LEEWAY_SECONDS,
                options={"require": ["exp", "iat", "iss", "aud", "sub"]},
            )
        except jwt.PyJWTError as exc:
            raise GoogleError(f"the ID token does not check out: {exc}") from exc
        if claims.get("iss") not in ISSUERS:
            raise GoogleError("the ID token was not issued by Google")
        if not secrets.compare_digest(str(claims.get("nonce", "")), nonce):
            raise GoogleError("the ID token was not made for this sign-in")
        email = claims.get("email")
        if not isinstance(email, str) or "@" not in email:
            raise GoogleError("Google did not say which address the account has")
        verified = claims.get("email_verified")
        return GoogleAccount(
            sub=str(claims["sub"]),
            email=email.strip().lower(),
            email_verified=verified is True or verified == "true",
        )


async def begin(
    session: AsyncSession,
    google: GoogleOAuth,
    purpose: OAuthPurpose,
    *,
    lang: str,
    next_path: str | None,
    now: datetime | None = None,
) -> Start:
    """Remember a sign-in about to start, and where to send the browser for it."""
    now = now or datetime.now(UTC)
    state = secrets.token_urlsafe(32)
    browser = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)  # 86 characters: PKCE allows 43 to 128
    nonce = secrets.token_urlsafe(32)
    session.add(
        OAuthState(
            state_hash=hash_token(state),
            browser_hash=hash_token(browser),
            code_verifier=verifier,
            nonce=nonce,
            purpose=purpose.value,
            lang=lang,
            next_path=next_path,
            created_at=now,
            expires_at=now + STATE_VALID_FOR,
        )
    )
    await session.flush()
    return Start(
        url=google.authorization_url(state=state, verifier=verifier, nonce=nonce), browser=browser
    )


async def claim(
    session: AsyncSession, state: str | None, browser: str | None, *, now: datetime | None = None
) -> OAuthState:
    """The sign-in this ``state`` belongs to, used up. Raises GoogleError when it is missing,
    unknown, expired, already used, or started in another browser."""
    now = now or datetime.now(UTC)
    if not state:
        raise GoogleError("Google came back without a state")
    row = await session.scalar(
        select(OAuthState).where(OAuthState.state_hash == hash_token(state)).with_for_update()
    )
    if row is None or row.used_at is not None or row.expires_at <= now:
        raise GoogleError("this sign-in is unknown, expired or already used")
    row.used_at = now  # spent even if what follows fails: a state is never tried twice
    await session.flush()
    if not browser or not secrets.compare_digest(row.browser_hash, hash_token(browser)):
        raise GoogleError("this sign-in was started in another browser")
    return row


async def sign_in(
    session: AsyncSession, account: GoogleAccount, *, now: datetime | None = None
) -> Reader:
    """The reader this Google account signs in as (see the module for the rules)."""
    now = now or datetime.now(UTC)
    linked = await session.scalar(
        select(ReaderIdentity).where(
            ReaderIdentity.provider == Provider.GOOGLE.value, ReaderIdentity.subject == account.sub
        )
    )
    if linked is not None:
        reader = await session.get(Reader, linked.reader_id)
        assert reader is not None
        return reader
    if not account.email_verified:
        raise SignInRefused(EMAIL_NOT_VERIFIED)
    try:
        reader = await by_email(session, account.email)  # the exact address, normalised alike
    except AccountError as exc:
        raise GoogleError("Google gave an address this site cannot use") from exc
    if reader is None:
        reader = Reader(email=account.email)
        session.add(reader)
        await session.flush()
    else:
        if await identity(session, reader.id, Provider.GOOGLE) is not None:
            raise SignInRefused(ANOTHER_GOOGLE_LINKED)
        # the reader's own address identity, proven by this site's own check — never Google's
        # word about an address a reader here registered, and never anything but this address
        own = await identity(session, reader.id, Provider.EMAIL)
        if own is None or own.verified_at is None or own.subject != account.email:
            raise SignInRefused(ADDRESS_NOT_PROVEN)
    session.add(
        ReaderIdentity(
            reader_id=reader.id,
            provider=Provider.GOOGLE.value,
            subject=account.sub,
            email=account.email,
            verified_at=now,
        )
    )
    await session.flush()
    return reader
