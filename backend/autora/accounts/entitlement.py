"""What a visitor may do on the site, decided here and nowhere else (P2, D-218, D-228).

The site's pages, the paywall and ``/api/auth/me`` all ask this module; the browser shows what
it answers and never works VIP out for itself.

- **Tier** is who they are to the site: ``public`` (not signed in), ``free`` (signed in), or
  ``vip`` (signed in, and a membership of this company still running — bought or given; where it
  came from does not matter, only that it is running, D-228).
- **Admin** is apart from the tier: an address on ADMIN_EMAILS that is proven (D-230). It says
  the back office may be opened; it reads no VIP article by itself.
- **Capabilities** are what the tier and admin allow. Only what P2 needs is here.

Buying is closed in P2: nobody has ``buy_membership``, and the API refuses checkout whatever
the catalogue says, until P8 opens payments (D-218, D-231).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from autora.accounts.credentials import email_verified
from autora.accounts.models import Reader
from autora.accounts.service import customer_ref
from autora.company import memberships

if TYPE_CHECKING:
    import uuid
    from collections.abc import Iterable

    from sqlalchemy.ext.asyncio import AsyncSession

CHECKOUT_OPEN = False
"""Whether membership may be bought (D-218, D-231): not in P2 — VIP is given (admin_comp) for
testing. P8 opens it, with the real payment; nothing else may, an env var or a configured shop
included. The catalogue's prices (NT$30 a month, NT$300 a year, D-161, D-231) are shown, not
sold."""


class Tier(StrEnum):
    PUBLIC = "public"
    FREE = "free"
    VIP = "vip"


class Capability(StrEnum):
    READ_SIGN_IN_SECTIONS = "read_sign_in_sections"
    """持股觀察 in full (D-159): any signed-in reader."""
    WATCHLIST = "watchlist"
    """A watchlist of one's own (D-060): any signed-in reader."""
    COINS = "coins"
    """A wallet of Whale Coins to look at (P3-C): any signed-in reader."""
    READ_VIP_ARTICLES = "read_vip_articles"
    """VIP articles in full: a running membership."""
    BUY_MEMBERSHIP = "buy_membership"
    """Checkout. Nobody, while ``CHECKOUT_OPEN`` is false."""
    ADMIN = "admin"
    """The back office may be opened (signing in to it is still its own step)."""


@dataclass(frozen=True)
class Entitlement:
    tier: Tier
    is_admin: bool = False
    vip_until: datetime | None = None
    """When the running membership ends; None unless ``vip``."""

    @property
    def capabilities(self) -> frozenset[Capability]:
        allowed: set[Capability] = set()
        if self.tier in (Tier.FREE, Tier.VIP):
            allowed |= {Capability.READ_SIGN_IN_SECTIONS, Capability.WATCHLIST, Capability.COINS}
            if CHECKOUT_OPEN:
                allowed.add(Capability.BUY_MEMBERSHIP)
        if self.tier == Tier.VIP:
            allowed.add(Capability.READ_VIP_ARTICLES)
        if self.is_admin:
            allowed.add(Capability.ADMIN)
        return frozenset(allowed)

    def can(self, capability: Capability) -> bool:
        return capability in self.capabilities


PUBLIC = Entitlement(tier=Tier.PUBLIC)


async def admin_authorized(
    session: AsyncSession, reader: Reader, admin_emails: Iterable[str]
) -> bool:
    """Authorization, apart from how they signed in (D-230): an address on ADMIN_EMAILS **and**
    proven to be theirs."""
    return reader.email in set(admin_emails) and await email_verified(session, reader)


async def entitlement_for(
    session: AsyncSession,
    reader: Reader | None,
    *,
    company_id: uuid.UUID | None,
    admin_emails: Iterable[str] = (),
    at: datetime | None = None,
) -> Entitlement:
    """What this reader (or nobody) may do on this company's site, now."""
    if reader is None:
        return PUBLIC
    until = None
    if company_id is not None:
        until = await memberships.access_until(
            session,
            company_id=company_id,
            customer_ref=customer_ref(reader.id),
            at=at or datetime.now(UTC),
        )
    return Entitlement(
        tier=Tier.VIP if until is not None else Tier.FREE,
        is_admin=await admin_authorized(session, reader, admin_emails),
        vip_until=until,
    )
