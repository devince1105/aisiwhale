"""Who gets how many coins a month, and when (P3-B; D-218, D-222, D-235).

Every number of the monthly grant is here and nowhere else. Changing one is a decision of its own
(a new D row and a deploy), not an environment variable; ``POLICY_VERSION`` changes with it and
is written on every grant, so a month can always be traced to the rules it was given under.

The ledger (``ledger.py``) knows none of this: it is told an amount, a cap and a key.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from autora.accounts.entitlement import Tier

MONTHLY_GRANTS_ON = False
"""Whether ``/api/auth/me`` gives the month's coins. Off until P3-C shows readers their wallet:
a coin written cannot be taken back, and the first grant should be one a reader can see. Turning
it on is a decision of its own and a deploy, like ``entitlement.CHECKOUT_OPEN``."""

POLICY_VERSION = "p3b-2"

GRANT_ZONE = ZoneInfo("Asia/Taipei")
"""A month starts at 00:00 on the 1st in Taipei (D-235 ②) — 16:00 UTC the day before."""


@dataclass(frozen=True)
class MonthlyGrant:
    amount: int
    """Given each month, up to the cap."""
    cap: int
    """No monthly grant raises the wallet past this."""


MONTHLY: dict[Tier, MonthlyGrant] = {
    Tier.FREE: MonthlyGrant(amount=50, cap=300),
    Tier.VIP: MonthlyGrant(amount=500, cap=3000),
}
"""D-218's monthly amounts; the caps are six months of them (raised from two, before any coin
was given). A tier not here (``public``) gets nothing."""


def eligible(tier: Tier, email_verified: bool) -> bool:
    """D-222 and D-235 ⑥: a signed-in reader of a tier that has a grant, whose address is
    proven (Google's word counts). "Signed in this month" is the trigger itself: only a signed-in
    request reaches it."""
    return tier in MONTHLY and email_verified


def month_of(now: datetime) -> str:
    """``YYYY-MM`` in Taipei."""
    return now.astimezone(GRANT_ZONE).strftime("%Y-%m")


def grant_key(tier: Tier, reader_id: uuid.UUID, month: str) -> str:
    """One grant per tier per reader per month: FREE then VIP in one month is two keys
    (D-235 ⑤); VIP again after that is the first key again."""
    return f"grant:{tier.value}:{reader_id}:{month}"
