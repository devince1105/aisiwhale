"""Readers, the tokens emailed to them, and their sessions (D-025, D-230).

Signing in is ``credentials`` (an address and a password) or ``google``; both end here, in a
session. This module keeps the parts they share:

- **Tokens are random and stored hashed.** What is in the database cannot be used — not a
  session, not a token from an email.
- **An emailed token is valid once, for its own purpose, for a while.** Redeeming one marks it
  used in the same transaction that acts on it, so a link opened twice works once; a token made
  to check an address cannot set a password.
- **Failures all say the same thing.** Unknown, expired, used, or for something else: telling
  them apart helps nobody but somebody guessing.

The emailed sign-in link (D-025) is retired as a way in (D-230); its rows stay in
``login_tokens`` with the purpose ``login``, and nothing redeems them any more.
"""

from __future__ import annotations

import hashlib
import re
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from autora.accounts.models import LoginToken, Reader, ReaderSession, TokenPurpose

ADDRESS_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
"""What counts as an address here: no spaces, one @, a dot after it. Deliberately loose —
the real check is whether a link sent to it arrives."""

SESSION_VALID_FOR = timedelta(days=60)
SESSION_COOKIE = "autora_reader"


class AccountError(Exception):
    pass


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def normalise(email: str) -> str:
    """One person, one spelling: trimmed and lowercased. Nothing else is rewritten — dots and
    ``+tags`` are part of an address, and merging them would merge different people."""
    email = email.strip().lower()
    if len(email) > 254 or not re.match(ADDRESS_PATTERN, email):
        raise AccountError(f"{email!r} is not an address a link can be sent to")
    return email


async def by_email(session: AsyncSession, email: str) -> Reader | None:
    return await session.scalar(select(Reader).where(Reader.email == normalise(email)))


async def issue_token(
    session: AsyncSession,
    reader: Reader,
    purpose: TokenPurpose,
    valid_for: timedelta,
    *,
    now: datetime | None = None,
) -> str:
    """A one-time token for this reader and purpose. The token itself is returned, to be put in
    an email; only its hash is kept."""
    now = now or datetime.now(UTC)
    token = secrets.token_urlsafe(32)
    # created_at from the same clock as expires_at, not the database's own: the table checks
    # expires_at > created_at, and two clocks — a caller's ``now``, the server's now() — can
    # disagree by more than a short token lives
    session.add(
        LoginToken(
            reader_id=reader.id,
            purpose=purpose.value,
            token_hash=hash_token(token),
            created_at=now,
            expires_at=now + valid_for,
        )
    )
    await session.flush()
    return token


async def redeem_token(
    session: AsyncSession, token: str, purpose: TokenPurpose, *, now: datetime | None = None
) -> Reader:
    """Use up a token for its purpose. Returns its reader; raises, always alike, if it cannot be."""
    now = now or datetime.now(UTC)
    row = await session.scalar(
        select(LoginToken).where(LoginToken.token_hash == hash_token(token)).with_for_update()
    )
    if row is None or row.purpose != purpose or row.used_at is not None or row.expires_at <= now:
        raise AccountError("this link no longer works; ask for a new one")
    row.used_at = now
    reader = await session.get(Reader, row.reader_id)
    assert reader is not None
    await session.flush()
    return reader


async def retire_tokens(
    session: AsyncSession, reader_id: uuid.UUID, purpose: TokenPurpose, *, now: datetime
) -> None:
    """Mark every unused token of this purpose used: once one has worked, the others must not."""
    await session.execute(
        update(LoginToken)
        .where(
            LoginToken.reader_id == reader_id,
            LoginToken.purpose == purpose.value,
            LoginToken.used_at.is_(None),
        )
        .values(used_at=now)
    )


async def start_session(
    session: AsyncSession,
    reader: Reader,
    *,
    now: datetime | None = None,
    valid_for: timedelta = SESSION_VALID_FOR,
) -> str:
    """A new signed-in browser. Returns the token for its cookie; only its hash is kept."""
    now = now or datetime.now(UTC)
    reader.last_seen_at = now
    session_token = secrets.token_urlsafe(32)
    session.add(
        ReaderSession(
            reader_id=reader.id,
            token_hash=hash_token(session_token),
            created_at=now,  # one clock, as for tokens
            expires_at=now + valid_for,
        )
    )
    await session.flush()
    return session_token


async def reader_for(
    session: AsyncSession, session_token: str | None, *, now: datetime | None = None
) -> Reader | None:
    """Who is holding this cookie, if anybody still is."""
    if not session_token:
        return None
    now = now or datetime.now(UTC)
    row = await session.scalar(
        select(ReaderSession).where(ReaderSession.token_hash == hash_token(session_token))
    )
    if row is None or row.revoked_at is not None or row.expires_at <= now:
        return None
    reader = await session.get(Reader, row.reader_id)
    if reader is not None:
        reader.last_seen_at = now
    return reader


async def sign_out(
    session: AsyncSession, session_token: str | None, *, now: datetime | None = None
) -> bool:
    if not session_token:
        return False
    row = await session.scalar(
        select(ReaderSession).where(ReaderSession.token_hash == hash_token(session_token))
    )
    if row is None or row.revoked_at is not None:
        return False
    row.revoked_at = now or datetime.now(UTC)
    await session.flush()
    return True


async def sign_out_everywhere(
    session: AsyncSession, reader_id: uuid.UUID, *, now: datetime | None = None
) -> None:
    """End every session of this reader: a new password must lock out whoever had the old one."""
    await session.execute(
        update(ReaderSession)
        .where(ReaderSession.reader_id == reader_id, ReaderSession.revoked_at.is_(None))
        .values(revoked_at=now or datetime.now(UTC))
    )


def customer_ref(reader_id: uuid.UUID) -> str:
    """How the company knows a reader: a reference, never an address (D-018, D-024)."""
    return f"reader:{reader_id}"
