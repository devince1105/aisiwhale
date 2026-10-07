"""Taiwan's three institutional investors — 三大法人 — stock by stock, day by day (HD-12, D-217):
what 13F is for the US, for Taiwan, from the exchanges themselves, every trading day.

Each trading day, for every listed (TWSE) and over-the-counter (TPEx) security, its net buying in
shares by **foreign investors** (外資, with the foreign dealers: TPEx's 外資及陸資合計), by
**investment trusts** (投信) and by **dealers** (自營商, on their own account and hedging), and the
three together; and its **foreign ownership ratio** (外資持股比率). Four documents a day, each
asked for by date:

- TWSE ``fund/T86``: 三大法人買賣超日報;
- TWSE ``fund/MI_QFIIS``: 外資及陸資投資持股統計;
- TPEx ``insti/dailyTrade``: 三大法人買賣明細資訊;
- TPEx ``insti/qfii``: 僑外資及陸資持股比例排行表.

**The runs are short**: TWSE answers a burst with a block, so a run asks ``REQUESTS_PER_RUN``
documents ``price_history.PAUSE_SECONDS`` apart, the latest day first, back ``BACKFILL_DAYS``;
every quarter of an hour of a shift. A day's documents come out in the late afternoon: today's not
out yet is asked for again; a weekday's with nothing in it is a holiday (``tw_flow_reads`` keeps
both, so neither is asked twice). Days older than ``KEEP_DAYS`` are dropped.

These are facts the exchanges publish, shown as they are — who bought, who sold — never advice.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Literal

from pydantic import BaseModel
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from autora.db.models import Schedule
from autora.domains.newsroom.models import TwFlow, TwFlowRead
from autora.runtime.scheduler import Handler

log = logging.getLogger(__name__)

FLOWS_SCHEDULE = "newsroom.refresh_tw_flows"
FLOWS_CRON = "*/15 7-13 * * 1-5"
"""Every quarter of an hour, 15:00 to 21:45 Taipei, weekdays: the documents come out from 16:00."""
TWSE_FLOWS = "https://www.twse.com.tw/rwd/zh/fund/T86"
TWSE_RATIOS = "https://www.twse.com.tw/rwd/zh/fund/MI_QFIIS"
TPEX_FLOWS = "https://www.tpex.org.tw/www/zh-tw/insti/dailyTrade"
TPEX_RATIOS = "https://www.tpex.org.tw/www/zh-tw/insti/qfii"
SOURCES = ("twse_flows", "tpex_flows", "twse_ratios", "tpex_ratios")
REQUESTS_PER_RUN = 8
BACKFILL_DAYS = 45
"""Calendar days back to read: some thirty trading days, so a stock page has twenty to sum."""
KEEP_DAYS = 70
INSERT_ROWS = 1000

GetJson = Callable[[str, dict], Awaitable[dict]]


class FlowsError(Exception):
    pass


# --- what the exchanges say ----------------------------------------------------------------------


@dataclass(frozen=True)
class Flow:
    symbol: str
    name: str
    foreign: int
    trust: int
    dealer: int
    total: int


@dataclass(frozen=True)
class Ratio:
    symbol: str
    issued: int | None
    held: int | None
    pct: Decimal | None


def _int(text: object) -> int:
    try:
        return int(str(text).replace(",", "").strip() or 0)
    except ValueError as exc:
        raise FlowsError(f"not a number of shares: {text!r}") from exc


def _pct(text: object) -> Decimal | None:
    shown = str(text).replace("%", "").replace(",", "").strip()
    try:
        return Decimal(shown) if shown else None
    except InvalidOperation:
        return None


def _rows(body: dict) -> list[list] | None:
    """A document's rows; None when it has none for the day (a holiday, or not out yet)."""
    tables = body.get("tables")
    if isinstance(tables, list):
        rows = [r for t in tables if isinstance(t, dict) for r in (t.get("data") or [])]
    else:
        rows = body.get("data") or []
    return rows or None


def parse_twse_flows(body: dict) -> list[Flow] | None:
    """T86: foreign investors (col 4) and the foreign dealers (7) together, trusts (10),
    dealers (11), the three (18)."""
    rows = _rows(body)
    if rows is None:
        return None
    return [
        Flow(
            symbol=str(r[0]).strip(),
            name=str(r[1]).strip(),
            foreign=_int(r[4]) + _int(r[7]),
            trust=_int(r[10]),
            dealer=_int(r[11]),
            total=_int(r[18]),
        )
        for r in rows
        if len(r) >= 19
    ]


def parse_tpex_flows(body: dict) -> list[Flow] | None:
    """dailyTrade: foreign investors with their dealers (col 10), trusts (13), dealers (22), the
    three (23)."""
    rows = _rows(body)
    if rows is None:
        return None
    return [
        Flow(
            symbol=str(r[0]).strip(),
            name=str(r[1]).strip(),
            foreign=_int(r[10]),
            trust=_int(r[13]),
            dealer=_int(r[22]),
            total=_int(r[23]),
        )
        for r in rows
        if len(r) >= 24
    ]


def parse_twse_ratios(body: dict) -> list[Ratio] | None:
    """MI_QFIIS: issued (col 3), held by foreign investors (5), their ratio (7)."""
    rows = _rows(body)
    if rows is None:
        return None
    return [
        Ratio(symbol=str(r[0]).strip(), issued=_int(r[3]), held=_int(r[5]), pct=_pct(r[7]))
        for r in rows
        if len(r) >= 8
    ]


def parse_tpex_ratios(body: dict) -> list[Ratio] | None:
    """qfii: issued (col 3), held (5), ratio (7), after a rank."""
    rows = _rows(body)
    if rows is None:
        return None
    return [
        Ratio(symbol=str(r[1]).strip(), issued=_int(r[3]), held=_int(r[5]), pct=_pct(r[7]))
        for r in rows
        if len(r) >= 8
    ]


def _request(source: str, day: date) -> tuple[str, dict]:
    if source == "twse_flows":
        return TWSE_FLOWS, {
            "date": day.strftime("%Y%m%d"),
            "selectType": "ALLBUT0999",
            "response": "json",
        }
    if source == "twse_ratios":
        return TWSE_RATIOS, {
            "date": day.strftime("%Y%m%d"),
            "selectType": "ALLBUT0999",
            "response": "json",
        }
    if source == "tpex_flows":
        return TPEX_FLOWS, {
            "type": "Daily",
            "sect": "EW",
            "date": day.strftime("%Y/%m/%d"),
            "response": "json",
        }
    return TPEX_RATIOS, {"date": day.strftime("%Y/%m/%d"), "response": "json"}


def _dated(body: dict, day: date) -> bool:
    """The document is the day's: TPEx answers a day it has nothing for with its own date's
    empty table, TWSE with no data at all."""
    shown = str(body.get("date") or "")
    tables = body.get("tables")
    if isinstance(tables, list) and tables and isinstance(tables[0], dict):
        shown = str(tables[0].get("date") or shown)
    digits = "".join(c for c in shown if c.isdigit())
    if len(digits) == 7:  # ROC: 1151006
        digits = str(int(digits[:3]) + 1911) + digits[3:]
    return not digits or digits == day.strftime("%Y%m%d")


# --- the runs ------------------------------------------------------------------------------------


def _weekdays(first: date, last: date) -> list[date]:
    days = (first + timedelta(days=n) for n in range((last - first).days + 1))
    return [d for d in days if d.weekday() < 5]


async def _keep_flows(
    session: AsyncSession, day: date, exchange: str, flows: list[Flow], now: datetime
) -> None:
    for start in range(0, len(flows), INSERT_ROWS):
        statement = insert(TwFlow).values(
            [
                {
                    "day": day,
                    "symbol": f.symbol,
                    "exchange": exchange,
                    "name": f.name,
                    "foreign_net": f.foreign,
                    "trust_net": f.trust,
                    "dealer_net": f.dealer,
                    "total_net": f.total,
                    "read_at": now,
                }
                for f in flows[start : start + INSERT_ROWS]
            ]
        )
        await session.execute(
            statement.on_conflict_do_update(
                index_elements=["day", "symbol"],
                set_={
                    "exchange": statement.excluded.exchange,
                    "name": statement.excluded.name,
                    "foreign_net": statement.excluded.foreign_net,
                    "trust_net": statement.excluded.trust_net,
                    "dealer_net": statement.excluded.dealer_net,
                    "total_net": statement.excluded.total_net,
                    "read_at": statement.excluded.read_at,
                },
            )
        )


async def _keep_ratios(
    session: AsyncSession, day: date, exchange: str, ratios: list[Ratio], now: datetime
) -> None:
    for start in range(0, len(ratios), INSERT_ROWS):
        statement = insert(TwFlow).values(
            [
                {
                    "day": day,
                    "symbol": r.symbol,
                    "exchange": exchange,
                    "foreign_ratio": r.pct,
                    "foreign_shares": r.held,
                    "issued_shares": r.issued,
                    "read_at": now,
                }
                for r in ratios[start : start + INSERT_ROWS]
            ]
        )
        await session.execute(
            statement.on_conflict_do_update(
                index_elements=["day", "symbol"],
                set_={
                    "foreign_ratio": statement.excluded.foreign_ratio,
                    "foreign_shares": statement.excluded.foreign_shares,
                    "issued_shares": statement.excluded.issued_shares,
                },
            )
        )


PARSERS = {
    "twse_flows": parse_twse_flows,
    "tpex_flows": parse_tpex_flows,
    "twse_ratios": parse_twse_ratios,
    "tpex_ratios": parse_tpex_ratios,
}


async def refresh_flows(
    session: AsyncSession,
    get: GetJson,
    *,
    today: date,
    limit: int = REQUESTS_PER_RUN,
    pause: float = 2.5,
    now: datetime | None = None,
) -> int:
    """Up to ``limit`` of the documents not read yet, the latest day first. How many were read
    with rows in them. A failure ends the run; the next one goes on."""
    now = now or datetime.now(UTC)
    done = {
        (day, source)
        for day, source in (await session.execute(select(TwFlowRead.day, TwFlowRead.source))).all()
    }
    todo = [
        (day, source)
        for day in reversed(_weekdays(today - timedelta(days=BACKFILL_DAYS), today))
        for source in SOURCES
        if (day, source) not in done
    ][:limit]
    read = 0
    for n, (day, source) in enumerate(todo):
        if n and pause:
            await asyncio.sleep(pause)
        url, params = _request(source, day)
        try:
            body = await get(url, params)
            found = PARSERS[source](body) if _dated(body, day) else None
        except Exception as error:  # an exchange's bad hour: the next run asks again
            log.warning("tw flows: %s %s not read (%s); next run", source, day, error)
            break
        if found is None:
            if day >= today:
                continue  # not out yet: asked again next run
            rows = 0  # a holiday
        else:
            exchange = "TWSE" if source.startswith("twse") else "TPEx"
            if source.endswith("flows"):
                await _keep_flows(session, day, exchange, found, now)  # type: ignore[arg-type]
            else:
                await _keep_ratios(session, day, exchange, found, now)  # type: ignore[arg-type]
            rows = len(found)
            read += 1
        await session.execute(
            insert(TwFlowRead)
            .values(day=day, source=source, rows=rows, read_at=now)
            .on_conflict_do_nothing(index_elements=["day", "source"])
        )
    await session.execute(delete(TwFlow).where(TwFlow.day < today - timedelta(days=KEEP_DAYS)))
    await session.execute(
        delete(TwFlowRead).where(TwFlowRead.day < today - timedelta(days=KEEP_DAYS))
    )
    await session.flush()
    return read


class FlowsKeeper:
    def __init__(self, get: GetJson | None, *, pause: float = 2.5) -> None:
        self.get = get
        """The exchanges; None offline, and nobody is asked."""
        self.pause = pause

    def schedule_handler(self) -> Handler:
        """The ``newsroom.refresh_tw_flows`` handler."""

        async def handler(
            session: AsyncSession, schedule: Schedule, scheduled_for: datetime
        ) -> None:
            if self.get is None:
                return
            today = (datetime.now(UTC) + timedelta(hours=8)).date()  # Taipei's
            await refresh_flows(session, self.get, today=today, pause=self.pause)

        return handler


# --- a stock's page ------------------------------------------------------------------------------

DAYS_SHOWN = 10
SUMS = (5, 20)


class PublicFlowDay(BaseModel):
    day: date
    foreign: int | None
    trust: int | None
    dealer: int | None
    total: int | None
    """Shares bought less shares sold; None when that day's figures are not known."""
    foreign_ratio: float | None
    """Per cent of its issued shares held by foreign investors that day."""


class PublicFlowSum(BaseModel):
    days: int
    """The last this many trading days with figures."""
    foreign: int
    trust: int
    dealer: int
    total: int


class PublicTwFlows(BaseModel):
    days: list[PublicFlowDay]
    """The latest ``DAYS_SHOWN`` trading days, latest first."""
    sums: list[PublicFlowSum]
    foreign_ratio: float | None
    foreign_ratio_day: date | None
    foreign_ratio_change: float | None
    """In percentage points, against twenty trading days back; None with fewer days kept."""
    exchange: str | None


async def for_stock(session: AsyncSession, symbol: str) -> PublicTwFlows | None:
    """A Taiwan stock's last trading days of 三大法人; None when the exchanges have said nothing
    about it (not read yet, or not a security they report)."""
    rows = (
        await session.scalars(
            select(TwFlow)
            .where(TwFlow.symbol == symbol)
            .order_by(TwFlow.day.desc())
            .limit(max(SUMS))
        )
    ).all()
    if not rows:
        return None
    flowed = [r for r in rows if r.total_net is not None]
    rated = [r for r in rows if r.foreign_ratio is not None]
    latest = rated[0] if rated else None
    oldest = rated[-1] if len(rated) >= max(SUMS) else None  # "20 days" only when it is
    return PublicTwFlows(
        days=[
            PublicFlowDay(
                day=r.day,
                foreign=r.foreign_net,
                trust=r.trust_net,
                dealer=r.dealer_net,
                total=r.total_net,
                foreign_ratio=float(r.foreign_ratio) if r.foreign_ratio is not None else None,
            )
            for r in rows[:DAYS_SHOWN]
        ],
        sums=[
            PublicFlowSum(
                days=n,
                foreign=sum(r.foreign_net or 0 for r in flowed[:n]),
                trust=sum(r.trust_net or 0 for r in flowed[:n]),
                dealer=sum(r.dealer_net or 0 for r in flowed[:n]),
                total=sum(r.total_net or 0 for r in flowed[:n]),
            )
            for n in SUMS
            if len(flowed) >= n
        ],
        foreign_ratio=float(latest.foreign_ratio) if latest is not None else None,
        foreign_ratio_day=latest.day if latest is not None else None,
        foreign_ratio_change=(
            round(float(latest.foreign_ratio - oldest.foreign_ratio), 2)
            if latest is not None and oldest is not None
            else None
        ),
        exchange=rows[0].exchange,
    )


# --- the day's ranking ---------------------------------------------------------------------------

MIN_DAY_ROWS = 100
"""A day ranked has figures for this many securities at least: not one half read."""
Group = Literal["foreign", "trust", "dealer", "total"]
Side = Literal["buy", "sell"]
RANKED = 50


class PublicFlowRow(BaseModel):
    rank: int
    symbol: str
    name: str
    exchange: str
    net: int
    """Shares, the group's net buying (negative: selling)."""
    foreign_ratio: float | None


class PublicFlowRanking(BaseModel):
    day: date | None
    days: list[date]
    """The trading days that can be asked for, latest first."""
    group: Group
    side: Side
    rows: list[PublicFlowRow]


_COLUMNS = {
    "foreign": TwFlow.foreign_net,
    "trust": TwFlow.trust_net,
    "dealer": TwFlow.dealer_net,
    "total": TwFlow.total_net,
}


async def ranking(
    session: AsyncSession,
    *,
    day: date | None = None,
    group: Group = "foreign",
    side: Side = "buy",
    limit: int = RANKED,
) -> PublicFlowRanking:
    """A day's largest net buying (or selling) by one of the three, stocks only: an ETF (its code
    starts with 00) is left out, so the list is of companies."""
    days = list(
        (
            await session.scalars(
                select(TwFlow.day)
                .where(TwFlow.total_net.is_not(None))
                .group_by(TwFlow.day)
                .having(func.count() >= MIN_DAY_ROWS)
                .order_by(TwFlow.day.desc())
            )
        ).all()
    )
    shown = day if day in days else (days[0] if days else None)
    if shown is None:
        return PublicFlowRanking(day=None, days=[], group=group, side=side, rows=[])
    column = _COLUMNS[group]
    rows = (
        await session.scalars(
            select(TwFlow)
            .where(
                TwFlow.day == shown,
                column.is_not(None),
                column > 0 if side == "buy" else column < 0,
                ~TwFlow.symbol.startswith("00"),
            )
            .order_by(column.desc() if side == "buy" else column.asc(), TwFlow.symbol)
            .limit(limit)
        )
    ).all()
    return PublicFlowRanking(
        day=shown,
        days=days,
        group=group,
        side=side,
        rows=[
            PublicFlowRow(
                rank=n,
                symbol=r.symbol,
                name=r.name or r.symbol,
                exchange=r.exchange,
                net=int(getattr(r, column.key)),
                foreign_ratio=float(r.foreign_ratio) if r.foreign_ratio is not None else None,
            )
            for n, r in enumerate(rows, start=1)
        ],
    )
