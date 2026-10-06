"""Signing in with an address and a password, and proving the address (D-230).

- **Registering** makes a reader with an unverified address and a password, and sends a link to
  check the address. Registering an address that already has a reader changes nothing about
  that reader: its owner is emailed instead, and the answer is the same either way.
- **An unverified address is not to be trusted with anything that depends on owning it.** Its
  holder may sign in and read; it does not open the back office, and it never vouches for
  linking a Google account to the reader (D-230: somebody could have registered another
  person's address, waiting for them to arrive by Google).
- **Resetting a password proves the address** — the link went to it — so it verifies the
  address, replaces any password, and ends every session: whoever knew the old password, or
  registered the address first, is out.
- **Checking a password takes as long for an address with no account** (``passwords.verify``),
  and says only yes or no.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from autora.accounts import passwords
from autora.accounts.models import Provider, Reader, ReaderIdentity, TokenPurpose
from autora.accounts.service import (
    AccountError,
    by_email,
    issue_token,
    normalise,
    redeem_token,
    retire_tokens,
    sign_out_everywhere,
)

VERIFY_VALID_FOR = timedelta(hours=24)
RESET_VALID_FOR = timedelta(minutes=30)


@dataclass(frozen=True)
class Registration:
    """What registering came to. Either way the caller answers the same; only the email differs.

    ``verify_token`` is set for a new reader (send them the link to check the address); unset,
    the address already had a reader, whose owner is told somebody tried."""

    reader: Reader
    verify_token: str | None


async def identity(
    session: AsyncSession, reader_id: uuid.UUID, provider: Provider
) -> ReaderIdentity | None:
    return await session.scalar(
        select(ReaderIdentity).where(
            ReaderIdentity.reader_id == reader_id, ReaderIdentity.provider == provider.value
        )
    )


async def email_verified(session: AsyncSession, reader: Reader) -> bool:
    """Whether the reader's own address is proven: by a link we sent to it, or by Google saying
    so when it was linked. Each is its own identity; neither is mistaken for the other."""
    proven = await session.scalar(
        select(ReaderIdentity.id).where(
            ReaderIdentity.reader_id == reader.id,
            ReaderIdentity.email == reader.email,
            ReaderIdentity.verified_at.is_not(None),
        )
    )
    return proven is not None


async def register(
    session: AsyncSession, email: str, password: str, *, now: datetime | None = None
) -> Registration:
    """A new reader with this address and password, unverified. Raises for a bad address or a
    password that may not be set; an address that is taken is not an error (see the module)."""
    now = now or datetime.now(UTC)
    address = normalise(email)
    passwords.check_new(password)
    existing = await by_email(session, address)
    if existing is not None:
        return Registration(reader=existing, verify_token=None)
    reader = Reader(email=address)
    session.add(reader)
    await session.flush()
    session.add(
        ReaderIdentity(
            reader_id=reader.id,
            provider=Provider.EMAIL.value,
            subject=address,
            email=address,
            password_hash=passwords.hash_password(password),
            verified_at=None,
        )
    )
    await session.flush()
    token = await issue_token(session, reader, TokenPurpose.EMAIL_VERIFY, VERIFY_VALID_FOR, now=now)
    return Registration(reader=reader, verify_token=token)


async def authenticate(session: AsyncSession, email: str, password: str) -> Reader | None:
    """The reader whose password this is, or None — for a wrong password, an unknown address or
    an address with no password alike, in the same time."""
    try:
        address = normalise(email)
    except AccountError:
        passwords.verify(None, password)
        return None
    row = await session.scalar(
        select(ReaderIdentity).where(
            ReaderIdentity.provider == Provider.EMAIL.value, ReaderIdentity.subject == address
        )
    )
    stored = row.password_hash if row is not None else None
    if not passwords.verify(stored, password):
        return None
    assert row is not None and stored is not None
    if passwords.needs_rehash(stored):
        row.password_hash = passwords.hash_password(password)
    return await session.get(Reader, row.reader_id)


async def request_verification(
    session: AsyncSession, reader: Reader, *, now: datetime | None = None
) -> str | None:
    """A new link to check the reader's address; None when there is nothing left to check."""
    row = await identity(session, reader.id, Provider.EMAIL)
    if row is None or row.verified_at is not None:
        return None
    return await issue_token(session, reader, TokenPurpose.EMAIL_VERIFY, VERIFY_VALID_FOR, now=now)


async def verify_email(session: AsyncSession, token: str, *, now: datetime | None = None) -> Reader:
    """Mark the address proven. Signs nobody in: opening a link is not a way to sign in."""
    now = now or datetime.now(UTC)
    reader = await redeem_token(session, token, TokenPurpose.EMAIL_VERIFY, now=now)
    row = await identity(session, reader.id, Provider.EMAIL)
    if row is None:
        raise AccountError("this link no longer works; ask for a new one")
    if row.verified_at is None:
        row.verified_at = now
    await retire_tokens(session, reader.id, TokenPurpose.EMAIL_VERIFY, now=now)
    await session.flush()
    return reader


async def request_reset(
    session: AsyncSession, email: str, *, now: datetime | None = None
) -> tuple[Reader, str] | None:
    """A link to set a new password, for an address that has a reader; None for one that has
    not — and the caller answers the same either way."""
    try:
        reader = await by_email(session, email)
    except AccountError:
        return None
    if reader is None:
        return None
    token = await issue_token(
        session, reader, TokenPurpose.PASSWORD_RESET, RESET_VALID_FOR, now=now
    )
    return reader, token


async def reset_password(
    session: AsyncSession, token: str, password: str, *, now: datetime | None = None
) -> Reader:
    """Set the password the link was sent for. The address is proven by it; every other reset
    link and every session of the reader ends here."""
    now = now or datetime.now(UTC)
    passwords.check_new(password)  # before the token is spent, so a typo does not cost the link
    reader = await redeem_token(session, token, TokenPurpose.PASSWORD_RESET, now=now)
    row = await identity(session, reader.id, Provider.EMAIL)
    if row is None:  # came by Google, or never had a password: the address is theirs all the same
        row = ReaderIdentity(
            reader_id=reader.id,
            provider=Provider.EMAIL.value,
            subject=reader.email,
            email=reader.email,
        )
        session.add(row)
    row.password_hash = passwords.hash_password(password)
    if row.verified_at is None:
        row.verified_at = now
    await retire_tokens(session, reader.id, TokenPurpose.PASSWORD_RESET, now=now)
    await sign_out_everywhere(session, reader.id, now=now)
    await session.flush()
    return reader
