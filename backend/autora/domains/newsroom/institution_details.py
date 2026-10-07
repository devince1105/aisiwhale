"""An institution's quarter, from its whole 13F tables (HD-10, D-217): what 機構排行's page for
it shows.

The ranking (``thirteenf_index``) knows each filer's total from its cover page; a page for one
needs its holdings. Both quarters' tables are read as they download (``thirteenf_tables``), each
row added to its position, and from the two the results are worked out and kept — the largest
holdings, the biggest buys and sells, an estimate of what was bought and sold — never the rows.

**For whom**: the ranked quarter's 100 largest (``ranked_period``: the latest whose filings were
all due), worked out ahead; anybody else when a reader first opens them (``request``, ``queued``
until a run gets to it — the page says to come back in a few minutes, as a new stock's chart
does, D-061). Again when the quarter gets a new filing (an amendment).

**The estimate** of what was bought and sold is each stock's change in shares at its quarter-end
price (the price the table implies: value ÷ shares), added up: a new position is bought at its
value, one sold out is sold at the quarter before's. Only shares held long count — not options,
not principal amounts. Corporate actions are not trades, and the table does not say which they
were, so:

- **a split**: a holding whose price moved past ``PRICE_BAND`` while its shares moved by about
  a common ratio (``SPLITS``) the other way is compared split-adjusted — KLA's 10-for-1 in the
  second quarter of 2026, with its price doubling as well, would otherwise read as BlackRock
  buying US$34 billion of it (``split`` says the ratio);
- **a new CUSIP for the same issuer** (its first six characters): a spin-off, a merger of share
  classes, a reverse split — Honeywell's in 2026 read as US$11 billion sold — is ``uncertain``,
  on both sides: no trade is estimated for them, and they are counted. A price that moved past
  the band with no split to explain it moved with the market (Marvell tripled that quarter).

**The runs are short**: every ten minutes, institutions one after another until ``BUDGET``
seconds have gone (BlackRock's two tables, 23 MB each, take some ten).
"""

from __future__ import annotations

import logging
import time
from collections import Counter
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from autora.db.models import Schedule
from autora.domains.newsroom import thirteenf, thirteenf_index, thirteenf_tables
from autora.domains.newsroom.models import (
    InstitutionDetail,
    InstitutionDetailStatus,
    ThirteenFFiling,
)
from autora.infra.http import FetchRefused, FetchUnavailable
from autora.runtime.scheduler import Handler

log = logging.getLogger(__name__)

DETAILS_SCHEDULE = "newsroom.refresh_institution_details"
DETAILS_CRON = "5-59/10 * * * *"
"""Five minutes after the index's runs, so the two do not wait on each other."""
RANKED = 100
TOP = 50
MOVES = 10
BUDGET = 45.0
MAX_ATTEMPTS = 3
PRICE_BAND = (Decimal("0.6"), Decimal("1.67"))
"""A quarter's price change outside this is not the market's alone."""
SPLITS = (2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 15, 20, 25, 30, 35, 40, 50, 60, 75, 100, 150, 200, 250)
"""The ratios splits are made in (and reverse splits, the other way)."""
SPLIT_SHARES = Decimal("1.25")
"""Shares within this of the ratio × the quarter before's: a split, and some trading."""
SPLIT_MARKET = (Decimal("0.4"), Decimal("2.5"))
"""The split-adjusted price change a quarter's market may make (KLA doubled)."""

Fetch = Callable[[str], Awaitable[bytes]]


# --- the results ---------------------------------------------------------------------------------


@dataclass(frozen=True)
class Move:
    position: thirteenf.Position
    change: str
    """``new``, ``increased``, ``decreased``, ``sold_out``, ``unchanged``."""
    shares: int
    previous_shares: int
    value: int
    previous_value: int
    traded_usd: int | None
    """Bought (+) or sold (−) at the quarter-end price; None when ``uncertain``."""
    split: str | None = None
    """``10:1`` for a 10-for-1 split, ``1:10`` for a reverse split; shares compared after it."""

    @property
    def uncertain(self) -> bool:
        return self.traded_usd is None


@dataclass(frozen=True)
class Worked:
    value_usd: int
    stock_value_usd: int
    stocks: int
    previous_stock_value_usd: int | None
    net_bought_usd: int | None
    counts: dict[str, int]
    top: list[dict[str, Any]]
    bought: list[dict[str, Any]]
    sold: list[dict[str, Any]]


def _stocks(holdings: thirteenf.Holdings) -> dict[tuple[str, str, str], thirteenf.Position]:
    return {
        key: p
        for key, p in holdings.positions.items()
        if p.kind == "SH" and not p.put_call and p.amount > 0
    }


def _price(p: thirteenf.Position) -> Decimal:
    return Decimal(p.value) / p.amount


def _split(shares: int, previous: int, moved: Decimal) -> tuple[Decimal, str] | None:
    """The split a holding went through, when its shares and price say one: shares about a
    common ratio × the quarter before's (the nearest ratio, 10 rather than 9), and the price,
    adjusted for it, a market's move. The ratio, and how a reader writes it (``10:1``)."""
    ratio = Decimal(shares) / Decimal(previous)
    fits = [
        (k, label)
        for n in SPLITS
        for k, label in ((Decimal(n), f"{n}:1"), (1 / Decimal(n), f"1:{n}"))
        if 1 / SPLIT_SHARES <= ratio / k <= SPLIT_SHARES
        and SPLIT_MARKET[0] <= moved * k <= SPLIT_MARKET[1]
    ]
    return min(fits, key=lambda fit: abs((ratio / fit[0]).ln())) if fits else None


def _move(
    now: thirteenf.Position | None, before: thirteenf.Position | None, *, acted: bool = False
) -> Move:
    """What became of a holding. ``acted``: its issuer has another CUSIP in the other quarter
    (a corporate action), so no trade is estimated."""
    held = now or before
    assert held is not None
    shares, previous = (now.amount if now else 0), (before.amount if before else 0)
    value, previous_value = (now.value if now else 0), (before.value if before else 0)
    if before is None:
        return Move(held, "new", shares, 0, value, 0, None if acted else value)
    if now is None:
        sold = None if acted else -previous_value
        return Move(held, "sold_out", 0, previous, 0, previous_value, sold)
    moved = _price(now) / _price(before) if before.value else Decimal(1)
    ratio, split = Decimal(1), None
    if not PRICE_BAND[0] <= moved <= PRICE_BAND[1]:
        found = _split(shares, previous, moved)
        if found is not None:
            ratio, split = found
    adjusted = (Decimal(previous) * ratio).to_integral_value()
    change = "increased" if shares > adjusted else "decreased" if shares < adjusted else "unchanged"
    traded = None if acted else int((Decimal(shares) - adjusted) * _price(now))
    return Move(held, change, shares, previous, value, previous_value, traded, split)


def _row(move: Move, *, of: int | None = None) -> dict[str, Any]:
    p = move.position
    row: dict[str, Any] = {
        "cusip": p.cusip,
        "name": p.name,
        "title_of_class": p.title_of_class,
        "change": move.change,
        "shares": move.shares,
        "previous_shares": move.previous_shares,
        "value_usd": move.value,
        "previous_value_usd": move.previous_value,
        "traded_usd": move.traded_usd,
        "split": move.split,
    }
    if of is not None:
        row["weight_pct"] = round(move.value / of * 100, 2) if of else None
    return row


def summarize(now: thirteenf.Holdings, before: thirteenf.Holdings | None) -> Worked:
    """A quarter's results, in dollars, against the quarter before when it is known."""
    stocks = _stocks(now)
    stock_value = sum(p.value for p in stocks.values())
    if before is None:
        moves = [
            Move(p, "new", p.amount, 0, p.value, 0, None) for p in stocks.values()
        ]  # nothing to compare with: no change, and no estimate
        return Worked(
            value_usd=now.total_value,
            stock_value_usd=stock_value,
            stocks=len(stocks),
            previous_stock_value_usd=None,
            net_bought_usd=None,
            counts={},
            top=[
                {**_row(m, of=stock_value), "change": None, "traded_usd": None}
                for m in sorted(moves, key=lambda m: (-m.value, m.position.cusip))[:TOP]
            ],
            bought=[],
            sold=[],
        )
    previous = _stocks(before)

    # an issuer's class under a CUSIP this quarter that it did not have, while its other CUSIP
    # for the class went
    def issue(key: tuple[str, str, str], p: thirteenf.Position) -> tuple[str, str]:
        return key[0][:6], p.title_of_class.strip().upper()

    came = Counter(issue(k, stocks[k]) for k in stocks.keys() - previous.keys())
    went = Counter(issue(k, previous[k]) for k in previous.keys() - stocks.keys())
    # one CUSIP went and one came: the same holding renamed. Several of either (a filer that
    # writes every fund of one trust as ``ETF``) are trades, not one holding.
    acted = {i for i in came.keys() & went.keys() if came[i] == went[i] == 1}
    moves = [
        _move(
            stocks.get(key),
            previous.get(key),
            acted=(key not in stocks or key not in previous)
            and issue(key, stocks.get(key) or previous[key]) in acted,
        )
        for key in stocks.keys() | previous.keys()
    ]
    counts = {c: 0 for c in ("new", "increased", "decreased", "sold_out", "unchanged")}
    for m in moves:
        counts[m.change] += 1
    counts["uncertain"] = sum(m.uncertain for m in moves)
    held = sorted((m for m in moves if m.shares), key=lambda m: (-m.value, m.position.cusip))
    known = [m for m in moves if m.traded_usd]
    bought = sorted(
        (m for m in known if m.traded_usd > 0), key=lambda m: (-m.traded_usd, m.position.cusip)
    )
    sold = sorted(
        (m for m in known if m.traded_usd < 0), key=lambda m: (m.traded_usd, m.position.cusip)
    )
    return Worked(
        value_usd=now.total_value,
        stock_value_usd=stock_value,
        stocks=len(stocks),
        previous_stock_value_usd=sum(p.value for p in previous.values()),
        net_bought_usd=sum(m.traded_usd or 0 for m in moves),
        counts=counts,
        top=[_row(m, of=stock_value) for m in held[:TOP]],
        bought=[_row(m) for m in bought[:MOVES]],
        sold=[_row(m) for m in sold[:MOVES]],
    )


# --- reading a quarter ---------------------------------------------------------------------------


async def read_quarter(
    fetch: Fetch, chunks: thirteenf_tables.Chunks, filings: list[ThirteenFFiling]
) -> thirteenf.Holdings:
    """A quarter's filings' tables, whole, in dollars, as one; each filing's ``scale`` set from
    its whole table."""
    parts = []
    for filing in filings:
        url = await thirteenf_tables.table_url(fetch, filing.cik, filing.accession)
        table = await thirteenf_tables.read_table(chunks, url)
        rows_scale = thirteenf_tables.scale_of(table)
        # the rows' units for the holdings; the cover page's own for the ranking's total
        filing.scale = thirteenf_tables.total_scale(
            table, rows_scale, int(filing.entries or 0), int(filing.value_usd or 0)
        )
        parts.append(thirteenf_tables.scaled(table, rows_scale))
    return thirteenf.combine(parts)


async def work_out(
    session: AsyncSession,
    fetch: Fetch,
    chunks: thirteenf_tables.Chunks,
    cik: str,
    period: date,
    *,
    now: datetime,
) -> InstitutionDetail:
    """One filer's quarter, read and kept (``ready``), or why not (``failed`` after
    ``MAX_ATTEMPTS``). SEC answering slowly is the caller's: nothing is kept."""
    cik = cik.lstrip("0")
    detail = await session.get(InstitutionDetail, (cik, period))
    if detail is None:
        detail = InstitutionDetail(cik=cik, period=period, status=InstitutionDetailStatus.QUEUED)
        session.add(detail)
    filings = await thirteenf_index.quarter_of(session, cik, period)
    try:
        if not filings:
            raise thirteenf.FilingError(f"no 13F for {period}")
        holdings = await read_quarter(fetch, chunks, filings)
        before_period = thirteenf_index.previous_period(period)
        earlier = await thirteenf_index.quarter_of(session, cik, before_period)
        before = await read_quarter(fetch, chunks, earlier) if earlier else None
    except FetchUnavailable:
        raise
    except Exception as error:  # this institution's failure, not the run's (nor every next run's)
        if not isinstance(error, thirteenf.FilingError | FetchRefused):
            log.exception("institution details: %s %s could not be worked out", cik, period)
        detail.attempts += 1
        detail.error = f"{type(error).__name__}: {error}"[:500]
        if detail.attempts >= MAX_ATTEMPTS:
            detail.status = InstitutionDetailStatus.FAILED
        await session.flush()
        return detail
    worked = summarize(holdings, before)
    detail.status = InstitutionDetailStatus.READY
    detail.computed_at = now
    detail.error = None
    detail.accessions = [f.accession for f in filings]
    detail.previous_period = before_period if before is not None else None
    detail.in_thousands = holdings.in_thousands
    detail.value_usd = worked.value_usd
    detail.stock_value_usd = worked.stock_value_usd
    detail.stocks = worked.stocks
    detail.previous_stock_value_usd = worked.previous_stock_value_usd
    detail.net_bought_usd = worked.net_bought_usd
    detail.counts = worked.counts
    detail.top = worked.top
    detail.bought = worked.bought
    detail.sold = worked.sold
    await session.flush()
    return detail


# --- what is due ---------------------------------------------------------------------------------


async def request(
    session: AsyncSession, cik: str, period: date, *, now: datetime | None = None
) -> InstitutionDetail:
    """A reader opened a filer's page: its quarter, worked out already or queued."""
    now = now or datetime.now(UTC)
    await session.execute(
        insert(InstitutionDetail)
        .values(
            cik=cik.lstrip("0"),
            period=period,
            status=InstitutionDetailStatus.QUEUED.value,
            requested_at=now,
        )
        .on_conflict_do_nothing(index_elements=["cik", "period"])
    )
    detail = await session.get(InstitutionDetail, (cik.lstrip("0"), period), populate_existing=True)
    assert detail is not None
    return detail


async def due(session: AsyncSession, period: date, *, ranked: int = RANKED) -> list[str]:
    """Whose quarter to work out next: those readers asked for, the longest waiting first; then
    the ``ranked`` largest without it, or whose quarter has had a filing since."""
    rows = {
        d.cik: d
        for d in (
            await session.scalars(
                select(InstitutionDetail).where(InstitutionDetail.period == period)
            )
        ).all()
    }
    waiting = sorted(
        (d for d in rows.values() if d.status == InstitutionDetailStatus.QUEUED),
        key=lambda d: (d.requested_at or datetime.max.replace(tzinfo=UTC), d.cik),
    )
    out = [d.cik for d in waiting]
    for total in (await thirteenf_index.quarter_totals(session, period))[:ranked]:
        detail = rows.get(total.cik)
        if detail is None or (
            detail.status == InstitutionDetailStatus.READY
            and tuple(detail.accessions) != total.accessions
        ):
            out.append(total.cik)
    return list(dict.fromkeys(out))


class DetailsKeeper:
    def __init__(self, fetch: Fetch | None, chunks: thirteenf_tables.Chunks | None) -> None:
        self.fetch = fetch
        self.chunks = chunks
        """SEC, and its tables streamed; None offline, and nothing is worked out."""

    def schedule_handler(self) -> Handler:
        """The ``newsroom.refresh_institution_details`` handler: institutions one after another
        until ``BUDGET`` seconds have gone."""

        async def handler(
            session: AsyncSession, schedule: Schedule, scheduled_for: datetime
        ) -> None:
            if self.fetch is None or self.chunks is None:
                return
            await refresh_details(session, self.fetch, self.chunks)

        return handler


async def refresh_details(
    session: AsyncSession,
    fetch: Fetch,
    chunks: thirteenf_tables.Chunks,
    *,
    today: date | None = None,
    budget: float = BUDGET,
    clock: Callable[[], float] | None = None,
) -> int:
    """The ranked quarter's due institutions (``due``), until ``budget`` seconds have gone. How
    many were worked out. SEC answering slowly ends the run."""
    clock = clock or time.monotonic
    start = clock()
    period = thirteenf_index.ranked_period(today or datetime.now(UTC).date())
    done = 0
    for cik in await due(session, period):
        if clock() - start > budget:
            break
        try:
            detail = await work_out(session, fetch, chunks, cik, period, now=datetime.now(UTC))
        except FetchUnavailable as error:
            log.warning("institution details: SEC is slow (%s); next run", error)
            break
        done += detail.status == InstitutionDetailStatus.READY
    return done
