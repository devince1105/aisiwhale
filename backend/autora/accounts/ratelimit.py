"""How often somebody may try to sign in, register or reset (D-230).

Counted in the database, not in a process: a restart or a deploy does not forget, and a second
API instance would count the same tries. Each key is an action and who is trying — a network
(the caller's IP) and, where there is one, an address — kept only as a hash. A window is fixed:
its first try starts it, and the count starts over once it has passed.

The network is counted first, and an address only while its network is still allowed: one
network cannot fill the table with keys by trying a new address each time. Rows nobody has
touched for a day are swept whenever a new key is written.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from autora.accounts.service import hash_token


@dataclass(frozen=True)
class Limit:
    action: str
    per_ip: int
    per_email: int | None
    window: timedelta


REGISTER = Limit("register", per_ip=10, per_email=3, window=timedelta(hours=1))
LOGIN = Limit("login", per_ip=30, per_email=10, window=timedelta(minutes=15))
FORGOT_PASSWORD = Limit("forgot_password", per_ip=10, per_email=3, window=timedelta(hours=1))
RESET_PASSWORD = Limit("reset_password", per_ip=20, per_email=None, window=timedelta(hours=1))
VERIFY_EMAIL = Limit("verify_email", per_ip=30, per_email=None, window=timedelta(hours=1))
RESEND_VERIFICATION = Limit(
    "resend_verification", per_ip=10, per_email=3, window=timedelta(hours=1)
)
GOOGLE_START = Limit("google_start", per_ip=30, per_email=None, window=timedelta(minutes=15))
GOOGLE_CALLBACK = Limit("google_callback", per_ip=30, per_email=None, window=timedelta(minutes=15))

SWEEP_AFTER = timedelta(days=1)

_HIT = text(
    """
    INSERT INTO auth_rate_limits (key, window_start, count)
    VALUES (:key, :now, 1)
    ON CONFLICT (key) DO UPDATE SET
        count = CASE WHEN auth_rate_limits.window_start <= :expired THEN 1
                     ELSE auth_rate_limits.count + 1 END,
        window_start = CASE WHEN auth_rate_limits.window_start <= :expired THEN :now
                            ELSE auth_rate_limits.window_start END
    RETURNING count, (xmax = 0) AS inserted
    """
)


async def _hit(session: AsyncSession, key: str, window: timedelta, now: datetime) -> int:
    row = (
        await session.execute(_HIT, {"key": hash_token(key), "now": now, "expired": now - window})
    ).one()
    if row.inserted:
        await session.execute(
            text("DELETE FROM auth_rate_limits WHERE window_start < :old"),
            {"old": now - SWEEP_AFTER},
        )
    return int(row.count)


async def allow(
    session: AsyncSession,
    limit: Limit,
    *,
    ip: str,
    email: str | None = None,
    now: datetime | None = None,
) -> bool:
    """Count one try; False when it is one too many. The caller commits, so a try is counted
    even when what it tried then fails."""
    now = now or datetime.now(UTC)
    if await _hit(session, f"{limit.action}:ip:{ip}", limit.window, now) > limit.per_ip:
        return False
    if email is not None and limit.per_email is not None:
        address = email.strip().lower()
        if (
            await _hit(session, f"{limit.action}:email:{address}", limit.window, now)
            > limit.per_email
        ):
            return False
    return True
