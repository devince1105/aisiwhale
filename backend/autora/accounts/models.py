"""Who the readers are (D-024, D-025).

**The only place in this system that holds a person's identity.** An email address lives here
and nowhere else: not in the ledger, not on customers, not in any event payload, not in
anything an agent can read. ``.importlinter`` keeps it that way — no layer below may import
this package — and the company knows a reader only as ``customers.external_ref``, the string
``reader:<id>``.

The tables, each as small as it can be:

- ``readers``: an address and when it was last seen. One person, one row (D-230).
- ``reader_identities``: the ways that person proves who they are — an address and a password
  (only ever its Argon2id hash), or a Google account by its ``sub``.
- ``login_tokens``: a one-time token sent by email, stored hashed, valid for minutes: to check an
  address or to set a new password (D-230; until then they were sign-in links, D-025).
- ``reader_sessions``: the cookie's other half, also stored hashed, valid for weeks.
- ``oauth_states``: a Google sign-in in flight, used once.
- ``auth_rate_limits``: how often an address or a network has tried, per window.

Tokens are hashed because these rows are a way into somebody's account: a leaked database dump
should not be a leaked set of live sessions.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import CheckConstraint, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from autora.db.base import Base, CreatedAtMixin, IdMixin, TimestampMixin, check_in


class Provider(StrEnum):
    """How somebody proves who they are (D-230)."""

    EMAIL = "email"
    """An address and a password. Verified once a link sent to the address has been opened."""
    GOOGLE = "google"
    """A Google account, known by its ``sub``: Google's own id for it, which never changes even
    when the account's address does. Never by its address."""


class TokenPurpose(StrEnum):
    """What an emailed token is for. ``login`` is the retired sign-in link (D-025), kept so the
    rows it left are still what they were (D-230)."""

    LOGIN = "login"
    PASSWORD_RESET = "password_reset"
    EMAIL_VERIFY = "email_verify"


class OAuthPurpose(StrEnum):
    """Which door a Google sign-in came through: the site, or the back office (D-055)."""

    READER = "reader"
    ADMIN = "admin"


class Reader(IdMixin, TimestampMixin, Base):
    """Somebody who signs in to read. Identified by their address, nothing else."""

    __tablename__ = "readers"
    __table_args__ = (
        UniqueConstraint("email"),
        CheckConstraint("email = lower(email)", name="email_is_lowercase"),
        CheckConstraint("position('@' in email) > 1", name="email_has_an_at"),
    )

    email: Mapped[str]
    """Lowercased on the way in, so one person is one row however they typed it."""
    last_seen_at: Mapped[datetime | None]
    watchlist_started_at: Mapped[datetime | None]
    """When their watchlist was first filled with the site's defaults (D-062). Set once: a list
    they empty stays empty."""


class ReaderIdentity(IdMixin, TimestampMixin, Base):
    """One way a reader signs in (D-230). A reader has at most one of each kind.

    ``(provider, subject)`` is unique: an address, or a Google account, belongs to one reader.
    """

    __tablename__ = "reader_identities"
    __table_args__ = (
        UniqueConstraint("provider", "subject"),
        UniqueConstraint("reader_id", "provider"),
        check_in("provider", Provider),
        CheckConstraint("email = lower(email)", name="email_is_lowercase"),
        CheckConstraint(
            "provider = 'email' OR password_hash IS NULL", name="only_email_has_a_password"
        ),
        CheckConstraint("provider <> 'email' OR subject = email", name="email_subject_is_email"),
    )

    reader_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("readers.id"), index=True)
    provider: Mapped[str]
    subject: Mapped[str]
    """``email``: the address, lowercased. ``google``: the account's ``sub``."""
    email: Mapped[str]
    """The address this identity vouches for: the reader's own for ``email``; for ``google``, the
    one Google gave when it was linked (kept for the record, never used to find the identity)."""
    password_hash: Mapped[str | None]
    """Argon2id, ``email`` only. None: no password yet — an address that signed in with the old
    links, or a reader who came by Google — set through the reset flow, never by default."""
    verified_at: Mapped[datetime | None]
    """``email``: when a link sent to the address was opened (our own check, not Google's).
    ``google``: when it was linked, Google having said the address is verified. None: unproven —
    such an identity never opens the back office and never vouches for linking another."""


class LoginToken(IdMixin, CreatedAtMixin, Base):
    """A token sent to an address: valid once, for minutes or hours (D-025, D-230)."""

    __tablename__ = "login_tokens"
    __table_args__ = (
        UniqueConstraint("token_hash"),
        CheckConstraint("expires_at > created_at", name="expires_after_created"),
        check_in("purpose", TokenPurpose),
    )

    reader_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("readers.id"), index=True)
    purpose: Mapped[str] = mapped_column(server_default=TokenPurpose.LOGIN.value)
    """What opening it does. A token is only ever redeemed for its own purpose."""
    token_hash: Mapped[str]
    """SHA-256 of the token in the link. The token itself is only ever in the email."""
    expires_at: Mapped[datetime]
    used_at: Mapped[datetime | None]
    """Set the moment it is redeemed, so the same link cannot be used twice."""


class ReaderSession(IdMixin, CreatedAtMixin, Base):
    """A signed-in browser. The cookie holds the token; this holds its hash."""

    __tablename__ = "reader_sessions"
    __table_args__ = (
        UniqueConstraint("token_hash"),
        CheckConstraint("expires_at > created_at", name="expires_after_created"),
    )

    reader_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("readers.id"), index=True)
    token_hash: Mapped[str]
    expires_at: Mapped[datetime]
    revoked_at: Mapped[datetime | None]
    """Signing out. The row stays: when a session ended is worth knowing."""


class OAuthState(IdMixin, CreatedAtMixin, Base):
    """A Google sign-in between leaving for Google and coming back (D-230). Used once.

    ``state`` travels through Google and comes back; only its hash is here. ``browser_hash`` is
    the hash of a nonce kept in the starting browser's cookie, so a sign-in started by somebody
    else cannot be finished in this browser. The PKCE verifier never leaves the server.
    """

    __tablename__ = "oauth_states"
    __table_args__ = (
        UniqueConstraint("state_hash"),
        CheckConstraint("expires_at > created_at", name="expires_after_created"),
        check_in("purpose", OAuthPurpose),
    )

    state_hash: Mapped[str]
    browser_hash: Mapped[str]
    code_verifier: Mapped[str]
    nonce: Mapped[str]
    """Sent to Google and checked in the ID token it signs: that token was made for this attempt."""
    purpose: Mapped[str]
    lang: Mapped[str]
    next_path: Mapped[str | None]
    expires_at: Mapped[datetime]
    used_at: Mapped[datetime | None]


class AuthRateLimit(Base):
    """How many tries a key has made in its current window (D-230).

    A key is an action and who is trying — ``login:ip:<hash>``, ``login:email:<hash>`` — never a
    raw address. A window starts over when it has passed; rows not touched for a day are swept.
    """

    __tablename__ = "auth_rate_limits"

    key: Mapped[str] = mapped_column(primary_key=True)
    window_start: Mapped[datetime]
    count: Mapped[int]


class WatchlistItem(IdMixin, CreatedAtMixin, Base):
    """A stock a reader keeps an eye on (D-060). Theirs alone: kept with the reader, never with
    the company's data, and gone with them."""

    __tablename__ = "watchlist_items"
    __table_args__ = (
        UniqueConstraint("reader_id", "market", "symbol"),
        CheckConstraint("market in ('tw', 'us', 'market')", name="market"),
    )

    reader_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("readers.id", ondelete="CASCADE"), index=True
    )
    market: Mapped[str]
    symbol: Mapped[str]
    """As the site's stock pages name it: ``NVDA``, ``2330``; one of the strip's other figures
    (``market``) by its key: ``TAIEX``, ``BTC`` (D-062)."""
    position: Mapped[int] = mapped_column(server_default="0")
    """Where the reader put it (D-063): smallest first; a new one goes last."""
