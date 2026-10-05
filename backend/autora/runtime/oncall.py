"""On call (D-205): off its shifts, the worker comes in when a person has just done something.

The shifts (D-193) let the database sleep, but they also made a person wait: an article approved
at 23:43 was published at the next clock-in, hours later; a draft sent back at three in the
afternoon was rewritten in the evening. So, off duty, the worker asks the API once a minute
whether anyone has acted in the back office. The API answers from its own memory, so the
database sleeps through the question. When someone has, the worker comes in, does what there is
to do, and goes home when nothing is left — or when one call has lasted its limit.

Coming in is overtime, and overtime is limited the way 勞基法 limits it: so many hours a day and
so many a month. The hours are kept in ``worker_overtime`` — read when a call comes, written when
it ends, both times when a person has just woken the database anyway — so a deploy does not reset
the month's count.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from autora.db.models import WorkerOvertime

log = logging.getLogger(__name__)

AskForCall = Callable[[], Awaitable[datetime | None]]
"""When a person last acted in the back office, or None (nobody yet, or no answer)."""


def api_caller(
    url: str,
    token: str,
    *,
    timeout: float = 10.0,
    transport: httpx.AsyncBaseTransport | None = None,
) -> AskForCall:
    """Ask the API (``GET /api/office-hours/call``). A failure is no call: the shifts go on.
    ``transport``: the tests' way to the API in-process."""
    failing = False

    async def ask() -> datetime | None:
        nonlocal failing
        try:
            async with httpx.AsyncClient(timeout=timeout, transport=transport) as client:
                response = await client.get(url, headers={"Authorization": f"Bearer {token}"})
                response.raise_for_status()
                called = response.json().get("called_at")
        except (httpx.HTTPError, ValueError) as exc:
            if not failing:  # once, not once a minute
                log.warning("cannot ask %s whether anyone called (%s); shifts only", url, exc)
            failing = True
            return None
        if failing:
            log.info("asking %s again works", url)
        failing = False
        return datetime.fromisoformat(called) if called else None

    return ask


@dataclass
class Overtime:
    """How much overtime is left, and what a call used (勞基法: a day's and a month's limit)."""

    session_factory: async_sessionmaker[AsyncSession]
    day_limit: timedelta
    month_limit: timedelta
    zone: ZoneInfo = field(default_factory=lambda: ZoneInfo("Asia/Taipei"))

    async def used(self, now: datetime) -> tuple[timedelta, timedelta]:
        """Today's and this month's, in the shifts' time zone."""
        today = now.astimezone(self.zone).date()
        async with self.session_factory() as session:
            day = await session.scalar(
                select(WorkerOvertime.seconds).where(WorkerOvertime.day == today)
            )
            month = await session.scalar(
                select(func.coalesce(func.sum(WorkerOvertime.seconds), 0)).where(
                    WorkerOvertime.day >= today.replace(day=1), WorkerOvertime.day <= today
                )
            )
        return timedelta(seconds=day or 0), timedelta(seconds=int(month or 0))

    async def left(self, now: datetime) -> timedelta:
        day, month = await self.used(now)
        return max(timedelta(0), min(self.day_limit - day, self.month_limit - month))

    async def record(self, start: datetime, end: datetime) -> None:
        """Add a call's time to the days it fell on (one that runs past midnight counts twice)."""
        if end <= start:
            return
        spans: dict[date, int] = {}
        cursor = start.astimezone(self.zone)
        last = end.astimezone(self.zone)
        while cursor < last:
            midnight = datetime.combine(cursor.date() + timedelta(days=1), datetime.min.time())
            stop = min(last, midnight.replace(tzinfo=self.zone))
            spans[cursor.date()] = spans.get(cursor.date(), 0) + round(
                (stop - cursor).total_seconds()
            )
            cursor = stop
        async with self.session_factory() as session:
            for day, seconds in spans.items():
                added = {"seconds": WorkerOvertime.seconds + seconds, "updated_at": func.now()}
                await session.execute(
                    insert(WorkerOvertime)
                    .values(day=day, seconds=seconds)
                    .on_conflict_do_update(index_elements=[WorkerOvertime.day], set_=added)
                )
            await session.commit()


@dataclass
class Call:
    """One call: when it began, when it must end at the latest, and since when it has been idle."""

    started: datetime
    until: datetime
    idle_since: datetime | None = None

    def over(self, now: datetime, idle: timedelta) -> bool:
        return now >= self.until or (self.idle_since is not None and now - self.idle_since >= idle)
