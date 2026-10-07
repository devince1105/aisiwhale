"""The month's coins, given when a reader is seen (P3-B; D-222, D-235).

``grant_monthly`` decides whether this reader gets this month's grant for their tier now, and
hands the ledger the amount, the cap and the key. It looks the key up before taking any lock, so
the many ``/api/auth/me`` calls of a month cost one indexed read each; only the first of a tier's
month locks the wallet and writes. Two at once both reach the ledger, and the second finds the
first's grant there (``created=False``).

It neither commits nor catches: the caller (``/api/auth/me``) runs it in a transaction of its
own, after its own commit, and logs a failure rather than failing the request.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from autora.accounts.coins import policy
from autora.accounts.coins.ledger import Posted, grant
from autora.accounts.coins.models import CoinTxn, TxnKind
from autora.accounts.entitlement import Tier
from autora.runtime.actor import Actor

ACTOR = Actor.system("monthly-grant")


@dataclass(frozen=True)
class ThisMonth:
    """Where a reader's month stands for their tier: what it gives, and whether it was given."""

    month: str
    """``YYYY-MM`` in Taipei."""
    terms: policy.MonthlyGrant | None
    """The tier's grant; None for a tier that has none."""
    granted: bool
    """This tier's grant for this month is written (a 0 capped one included)."""


async def this_month(
    session: AsyncSession, reader_id: uuid.UUID, tier: Tier, *, now: datetime | None = None
) -> ThisMonth:
    """The month, the tier's terms and whether its grant is written — by the same key
    ``grant_monthly`` writes, so a wallet page and the grant never disagree. Reads only."""
    month = policy.month_of(now or datetime.now(UTC))
    terms = policy.MONTHLY.get(tier)
    if terms is None:
        return ThisMonth(month=month, terms=None, granted=False)
    key = policy.grant_key(tier, reader_id, month)
    found = await session.scalar(select(CoinTxn.id).where(CoinTxn.idempotency_key == key))
    return ThisMonth(month=month, terms=terms, granted=found is not None)


async def grant_monthly(
    session: AsyncSession,
    reader_id: uuid.UUID,
    *,
    tier: Tier,
    email_verified: bool,
    now: datetime | None = None,
    trigger: str = "auth_me",
) -> Posted | None:
    """This month's grant for ``tier``, or None when there is nothing to do: grants are off, the
    reader is not eligible, or this tier's month was given already."""
    if not policy.MONTHLY_GRANTS_ON or not policy.eligible(tier, email_verified):
        return None
    status = await this_month(session, reader_id, tier, now=now)
    if status.granted or status.terms is None:
        return None
    month, terms = status.month, status.terms
    key = policy.grant_key(tier, reader_id, month)
    return await grant(
        session,
        reader_id,
        requested=terms.amount,
        cap=terms.cap,
        idempotency_key=key,
        actor=ACTOR,
        kind=TxnKind.MONTHLY_GRANT,
        meta={
            "tier": tier.value,
            "month": month,
            "policy": policy.POLICY_VERSION,
            "monthly": terms.amount,
            "cap": terms.cap,
            "trigger": trigger,
        },
    )
