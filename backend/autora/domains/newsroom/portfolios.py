"""The holdings dashboard's numbers for each followed 13F filer (HD-04, D-217): its largest
holdings, the latest quarter's two biggest moves, and a simulated one-year return.

**The simulated return** is what the filer's disclosed portfolio would have earned, quarter by
quarter (``logs/holdings/01_HOLDINGS_PLAN.md`` §3.3):

1. it starts at the last quarter's end at least a year ago (on 2026-10-06, 2025-09-30);
2. each quarter's 13F is held, weighted by value, to the next quarter's end; the latest one to
   the latest price;
3. the quarters' returns compound;
4. long shares only — no options, no principal (bonds), no cash, nothing traded within a quarter,
   no dividends (prices, not total return), and a spin-off is not adjusted for (DuPont's of
   Qnity reads as a fall);
5. a holding with no price is left out and the rest weighted again; the least share of a
   stretch's value priced is the coverage, and under ``MIN_COVERAGE`` no number is given.

**Where the prices come from** — the free plans set the design. Measured 2026-10-06 over the
nine filers' year, the top 90% of each quarter: 384 distinct stocks, past Tiingo's 500 a month
and far past its 50 an hour. So:

- a quarter's end is priced by the 13Fs themselves: value over shares, from whichever followed
  filer held the stock then (the largest holding, the least rounded). 577 of the year's moves are
  priced so, with no request at all;
- Tiingo is asked only where the 13Fs cannot answer: a stock sold out that none of them holds at
  the next quarter's end (86 that year), and a move outside ``CHECK`` (95) — a split (Booking's 25
  for 1 reads 0.042) or a real fall (Atlassian, 0.42), which the 13Fs cannot tell apart. Its raw
  closes and split factors are kept (``raw_closes``), so a stretch is asked once; the largest
  holdings first, ``TIINGO_PER_RUN`` in each run, a run every twenty minutes;
- the latest price is Finnhub's quote, for the latest quarter's top ``PRICED_SHARE``; a move
  since the quarter's end outside ``CHECK`` is checked against Tiingo's splits too.

Only holdings within the top ``PRICED_SHARE`` of a quarter's value are asked about; the others
count when what is already known prices them.

**The moves** are the latest quarter's against the one before, the largest in dollars at the
quarter's end. A stock whose 13F price moved outside ``CHECK`` may have split — its shares then
change without a trade — so it waits until Tiingo's closes say how much it split.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from autora.db.models import Schedule
from autora.domains.newsroom import cusips
from autora.domains.newsroom.holdings import thirteenf_sources
from autora.domains.newsroom.models import (
    PortfolioPosition,
    PortfolioQuarter,
    PortfolioStat,
    PositionChange,
    PriceAsk,
    RawClose,
    Source,
    StockQuote,
)
from autora.domains.newsroom.price_history import TIINGO_DAILY, GetRows
from autora.runtime.scheduler import Handler

log = logging.getLogger(__name__)

STATS_SCHEDULE = "newsroom.refresh_portfolio_stats"
STATS_CRON = "*/20 * * * *"
"""Every twenty minutes of the worker's shifts (D-205), a little each time: a scheduler handler
holds up everything else the worker starts — its first version, all quotes and twenty Tiingo
stretches 75 s apart in one run, held new agent runs back half an hour on its first shift."""
RETRY = timedelta(days=30)
"""A stretch Tiingo could not answer is asked again after this."""

YEAR = timedelta(days=365)
CHECK = (Decimal("0.7"), Decimal("1.4"))
"""A quarter's price move the 13Fs are trusted with; outside it, a split is possible (a 3-for-2
reads 0.667) and Tiingo's closes and splits decide."""
MIN_COVERAGE = Decimal("0.8")
PRICED_SHARE = Decimal("0.9")
TIINGO_PER_RUN = 2
"""Six an hour: with the price refreshes' (D-059, up to 48 in an hour twice a weekday) inside
Tiingo's 50; about 36 stretches a weekday shift."""
TIINGO_PAUSE = 2.0
QUOTES_PER_RUN = 50
"""Finnhub quotes a run (75 s at ``QUOTE_PAUSE``): the latest quarter's top 90% — some 250
stocks — are all fresh within a shift."""
QUOTE_AGE = timedelta(hours=20)
"""A kept quote younger than this is not asked again: the market moves once a day."""
JUMP = Decimal("0.25")
"""A quote this far from the last kept close may be past a split since: the closes are asked
again."""
FRESH = timedelta(days=30)
"""Kept closes older than this do not vouch for a quote: asked again."""
STALE = timedelta(days=6)
"""A close more than this before a day is not that day's (a weekend and a holiday at most)."""
TOP = 10
MOVES = 2
QUOTE_PAUSE = 1.5
"""Between two Finnhub quotes: its free plan's 60 a minute, shared with the market strip."""


# --- what the 13Fs say --------------------------------------------------------------------------


@dataclass(frozen=True)
class Held:
    """A long position in shares: no options, no principal."""

    cusip: str
    issuer: str
    shares: int
    value: int


@dataclass(frozen=True)
class Quarter:
    period: date
    filed: date
    held: tuple[Held, ...]
    """Largest first."""

    @property
    def value(self) -> int:
        return sum(h.value for h in self.held)

    def top(self, share: Decimal = PRICED_SHARE) -> set[str]:
        """The CUSIPs making up ``share`` of its value, largest first."""
        whole, run, out = self.value, 0, set()
        for held in self.held:
            if run >= share * whole:
                break
            out.add(held.cusip)
            run += held.value
        return out


def quarter_end(day: date) -> date:
    """The last calendar quarter's end on or before ``day``."""
    for month, last in ((12, 31), (9, 30), (6, 30), (3, 31)):
        end = date(day.year, month, last)
        if end <= day:
            return end
    return date(day.year - 1, 12, 31)


def year_start(today: date) -> date:
    """Where a one-year return starts: the last quarter's end at least a year before today."""
    return quarter_end(today - YEAR)


# --- what the prices are ------------------------------------------------------------------------


@dataclass(frozen=True)
class Close:
    day: date
    close: Decimal
    split: Decimal = Decimal(1)


@dataclass(frozen=True)
class Quote:
    price: Decimal
    day: date


@dataclass
class Prices:
    """Everything known about prices in a run, and what the run would still like to know."""

    implied: dict[tuple[str, date], Decimal]
    """(CUSIP, quarter's end) → the 13Fs' price: value over shares."""
    symbols: dict[str, str]
    """CUSIP → US ticker (``cusips``)."""
    closes: dict[str, list[Close]] = field(default_factory=dict)
    """Ticker → Tiingo's raw closes, oldest first."""
    quotes: dict[str, Quote] = field(default_factory=dict)
    needs: dict[tuple[str, date, date | None], Decimal] = field(default_factory=dict)
    """(ticker, start, end — None to the latest) → the largest holding's weight that wants it."""
    quoted: set[str] = field(default_factory=set)
    """Tickers a latest stretch wants a quote for."""
    asked: set[tuple[str, date, date]] = field(default_factory=set)
    """Stretches Tiingo was asked for lately (``price_asks``; the latest one's end is the quote's
    day): what it could not answer then is not asked again, nor waited for."""
    wanted: int = 0
    """How many times a holding has wanted something only Tiingo can give: a filer's pending."""

    def _need(self, symbol: str, start: date, end: date | None, weight: Decimal) -> None:
        self.wanted += 1
        key = (symbol, start, end)
        self.needs[key] = max(weight, self.needs.get(key, Decimal(0)))

    def _close(self, symbol: str, day: date) -> int | None:
        """The index of the close that is ``day``'s: the last on or before it, not stale."""
        rows = self.closes.get(symbol) or []
        found = None
        for i, row in enumerate(rows):
            if row.day > day:
                break
            found = i
        if found is None or rows[found].day < day - STALE:
            return None
        return found

    def _split(self, symbol: str, after: int, through: int) -> Decimal:
        factor = Decimal(1)
        for row in (self.closes.get(symbol) or [])[after + 1 : through + 1]:
            factor *= row.split
        return factor

    def split_factor(self, symbol: str, start: date, end: date) -> Decimal | None:
        """How many shares one became between the two days, if the closes reach both."""
        a, b = self._close(symbol, start), self._close(symbol, end)
        if a is None or b is None:
            return None
        return self._split(symbol, a, b)

    def _tiingo(self, symbol: str, start: date, end: date) -> Decimal | None:
        a, b = self._close(symbol, start), self._close(symbol, end)
        if a is None or b is None:
            return None
        rows = self.closes[symbol]
        return rows[b].close * self._split(symbol, a, b) / rows[a].close

    def stretch(
        self, cusip: str, start: date, end: date, weight: Decimal, *, ask: bool
    ) -> Decimal | None:
        """A holding's price at ``end`` over its price at ``start``; None when unknown (and, if
        ``ask``, the stretch is wanted from Tiingo)."""
        before, after = self.implied.get((cusip, start)), self.implied.get((cusip, end))
        if before and after:
            ratio = after / before
            if CHECK[0] <= ratio <= CHECK[1]:
                return ratio
        symbol = self.symbols.get(cusip)
        if symbol is None:
            return None
        ratio = self._tiingo(symbol, start, end)
        if ratio is not None:
            return ratio
        if (symbol, start, end) in self.asked:
            return self._delisted(symbol, start, end)
        if ask:
            self._need(symbol, start, end, weight)
        return None

    def _delisted(self, symbol: str, start: date, end: date) -> Decimal | None:
        """A stock asked for that stopped trading between ``start`` and ``end`` — taken over, or
        delisted — was cash at its last close by ``end``."""
        a = self._close(symbol, start)
        rows = self.closes.get(symbol) or []
        if a is None or rows[-1].day <= rows[a].day or rows[-1].day >= end - STALE:
            return None
        return rows[-1].close * self._split(symbol, a, len(rows) - 1) / rows[a].close

    def latest(
        self, cusip: str, start: date, weight: Decimal, *, ask: bool
    ) -> tuple[Decimal, date] | None:
        """A holding's latest quote over its price at ``start``, and the quote's day."""
        symbol = self.symbols.get(cusip)
        if symbol is None:
            return None
        if ask:
            self.quoted.add(symbol)
        quote, before = self.quotes.get(symbol), self.implied.get((cusip, start))
        if quote is None or before is None:
            return None
        ratio = quote.price / before
        if CHECK[0] <= ratio <= CHECK[1]:
            return ratio, quote.day
        # a split since the quarter's end, or a move big enough to be checked: Tiingo's closes,
        # if they reach close enough to the quote that no split can have come between
        rows = self.closes.get(symbol) or []
        a = self._close(symbol, start)
        if (
            a is not None
            and rows[-1].day >= quote.day - FRESH
            and abs(quote.price / rows[-1].close - 1) <= JUMP
        ):
            return quote.price * self._split(symbol, a, len(rows) - 1) / rows[a].close, quote.day
        if ask and (symbol, start, quote.day) not in self.asked:
            self._need(symbol, start, None, weight)
        return None


# --- the numbers --------------------------------------------------------------------------------


@dataclass(frozen=True)
class Simulated:
    growth: Decimal | None
    """The return as a fraction; None when not given."""
    start: date | None
    through: date | None
    coverage: Decimal | None
    pending: int = 0
    """Holdings waiting for Tiingo: while any are, no number — the ones it is asked about are the
    biggest moves, and leaving them out would bend the return."""


def simulate(
    quarters: list[Quarter], prices: Prices, today: date, *, ask: bool = True
) -> Simulated:
    """The simulated one-year return of a filer's kept quarters (the module's rules 1–5)."""
    start = year_start(today)
    wanted_before = prices.wanted
    ordered = sorted(quarters, key=lambda q: q.period)
    before = [q for q in ordered if q.period <= start]
    if not before:
        return Simulated(None, None, None, None)  # not a year of 13Fs kept
    stretches = [(before[-1], start), *((q, q.period) for q in ordered if q.period > start)]
    growth, least, through = Decimal(1), Decimal(1), None
    for i, (quarter, begin) in enumerate(stretches):
        end = stretches[i + 1][1] if i + 1 < len(stretches) else None
        total = Decimal(quarter.value)
        if not total:
            return Simulated(None, start, None, Decimal(0))
        wanted = quarter.top() if ask else set()
        priced, grown = Decimal(0), Decimal(0)
        for held in quarter.held:
            weight = held.value / total
            if end is None:
                got = prices.latest(held.cusip, begin, weight, ask=held.cusip in wanted)
                ratio = got[0] if got else None
                if got:
                    through = max(through, got[1]) if through else got[1]
            else:
                ratio = prices.stretch(held.cusip, begin, end, weight, ask=held.cusip in wanted)
            if ratio is not None:
                priced += held.value
                grown += held.value * ratio
        least = min(least, priced / total)
        if priced:
            growth *= grown / priced
    pending = prices.wanted - wanted_before
    if least < MIN_COVERAGE or through is None or pending:
        return Simulated(None, start, through, least, pending)
    return Simulated(growth - 1, start, through, least)


@dataclass(frozen=True)
class Move:
    cusip: str
    issuer: str
    change: str
    shares: int
    previous_shares: int
    """Adjusted for a split between the two quarters."""
    value_change: int
    """US$, the shares bought or sold at the quarter's end price (sold out: the one before's)."""


def moves(
    latest: Quarter, previous: Quarter | None, prices: Prices, count: int = MOVES
) -> list[Move]:
    """The latest quarter's biggest moves against the one before (none bought or sold: none)."""
    if previous is None:
        return []
    now = {h.cusip: h for h in latest.held}
    before = {h.cusip: h for h in previous.held}
    out = []
    for cusip in now.keys() | before.keys():
        n, b = now.get(cusip), before.get(cusip)
        prev = b.shares if b else 0
        if n and b:
            p_now, p_before = (
                prices.implied.get((cusip, latest.period)),
                prices.implied.get((cusip, previous.period)),
            )
            if p_now and p_before and not CHECK[0] <= p_now / p_before <= CHECK[1]:
                symbol = prices.symbols.get(cusip)
                factor = (
                    prices.split_factor(symbol, previous.period, latest.period) if symbol else None
                )
                if factor is None:
                    continue  # it may have split: not a move until Tiingo says how much
                prev = int(prev * factor)
        shares = n.shares if n else 0
        if shares == prev:
            continue
        holding = n or b
        assert holding is not None
        price = Decimal(holding.value) / holding.shares if holding.shares else Decimal(0)
        change = (
            PositionChange.NEW
            if b is None
            else PositionChange.SOLD_OUT
            if n is None
            else PositionChange.INCREASED
            if shares > prev
            else PositionChange.DECREASED
        )
        out.append(
            Move(cusip, holding.issuer, change.value, shares, prev, int((shares - prev) * price))
        )
    return sorted(out, key=lambda m: (-abs(m.value_change), m.cusip))[:count]


@dataclass(frozen=True)
class Top:
    cusip: str
    issuer: str
    value: int
    weight: Decimal


def largest(quarter: Quarter, count: int = TOP) -> list[Top]:
    total = Decimal(quarter.value) or Decimal(1)
    return [Top(h.cusip, h.issuer, h.value, h.value / total) for h in quarter.held[:count]]


# --- the run ------------------------------------------------------------------------------------


GetQuote = Callable[[str], Awaitable[Quote | None]]
FINNHUB_QUOTE = "https://finnhub.io/api/v1/quote"


def finnhub_quote(get: Callable[[str, dict], Awaitable[dict]]) -> GetQuote:
    """Finnhub's quote of a US ticker (``economic_calendar.finnhub_json`` reads it): the last
    price and its day; None for a ticker it does not quote (it answers zeros)."""

    async def quote(symbol: str) -> Quote | None:
        data = await get(FINNHUB_QUOTE, {"symbol": symbol})
        price, at = data.get("c"), data.get("t")
        if not price or not at:
            return None
        return Quote(Decimal(str(price)), datetime.fromtimestamp(int(at), UTC).date())

    return quote


def parse_closes(rows: list[dict]) -> list[Close]:
    """Tiingo's daily rows, as traded (``close``, not ``adjClose``), with their split factors."""
    out = []
    for row in rows:
        try:
            out.append(
                Close(
                    day=date.fromisoformat(str(row["date"])[:10]),
                    close=Decimal(str(row["close"])),
                    split=Decimal(str(row.get("splitFactor") or 1)),
                )
            )
        except (KeyError, TypeError, ValueError, InvalidOperation):
            continue
    return sorted(out, key=lambda c: c.day)


async def _books(
    session: AsyncSession, company_id: uuid.UUID
) -> tuple[dict[uuid.UUID, list[Quarter]], dict[tuple[str, date], Decimal]]:
    """Each 13F source's kept quarters (long shares), and the 13Fs' prices pooled across them."""
    sources = (await session.scalars(select(Source).where(Source.company_id == company_id))).all()
    followed = {source.id for source, _ in thirteenf_sources(list(sources))}
    rows = await session.execute(
        select(PortfolioQuarter, PortfolioPosition)
        .join(PortfolioPosition, PortfolioPosition.quarter_id == PortfolioQuarter.id)
        .where(
            PortfolioQuarter.company_id == company_id,
            PortfolioPosition.kind == "SH",
            PortfolioPosition.put_call == "",
            PortfolioPosition.amount > 0,
        )
    )
    held: dict[uuid.UUID, tuple[PortfolioQuarter, list[Held]]] = {}
    largest_value: dict[tuple[str, date], int] = {}
    implied: dict[tuple[str, date], Decimal] = {}
    for quarter, position in rows.all():
        if quarter.source_id not in followed:
            continue
        h = Held(position.cusip, position.issuer, int(position.amount), int(position.value_usd))
        held.setdefault(quarter.id, (quarter, []))[1].append(h)
        key = (h.cusip, quarter.period)
        if h.value > largest_value.get(key, -1):
            largest_value[key] = h.value
            implied[key] = Decimal(h.value) / h.shares
    books: dict[uuid.UUID, list[Quarter]] = {}
    for quarter, positions in held.values():
        books.setdefault(quarter.source_id, []).append(
            Quarter(
                quarter.period,
                quarter.filed,
                tuple(sorted(positions, key=lambda h: (-h.value, h.cusip))),
            )
        )
    return books, implied


async def _closes(session: AsyncSession, symbols: set[str]) -> dict[str, list[Close]]:
    out: dict[str, list[Close]] = {}
    if not symbols:
        return out
    rows = await session.scalars(
        select(RawClose).where(RawClose.symbol.in_(symbols)).order_by(RawClose.day)
    )
    for row in rows.all():
        out.setdefault(row.symbol, []).append(Close(row.day, row.close, row.split_factor))
    return out


async def _keep_closes(session: AsyncSession, symbol: str, closes: list[Close]) -> None:
    if not closes:
        return
    statement = insert(RawClose).values(
        [
            {"symbol": symbol, "day": c.day, "close": c.close, "split_factor": c.split}
            for c in closes
        ]
    )
    await session.execute(
        statement.on_conflict_do_update(
            index_elements=["symbol", "day"],
            set_={
                "close": statement.excluded.close,
                "split_factor": statement.excluded.split_factor,
            },
        )
    )


def tiingo_symbol(symbol: str) -> str:
    """Tiingo writes a share class with a hyphen: ``BRK-B``."""
    return symbol.replace(".", "-")


async def refresh_portfolio_stats(
    session: AsyncSession,
    company_id: uuid.UUID,
    *,
    quote: GetQuote | None,
    tiingo: GetRows | None,
    today: date,
    quote_pause: float = QUOTE_PAUSE,
    tiingo_pause: float = TIINGO_PAUSE,
    tiingo_per_run: int = TIINGO_PER_RUN,
    quotes_per_run: int = QUOTES_PER_RUN,
    now: datetime | None = None,
) -> int:
    """Every followed 13F filer's card brought up to date: the quotes that are missing or old
    (``quotes_per_run``, the missing first), what Tiingo still owes (the largest holdings first,
    ``tiingo_per_run`` stretches), then the numbers. A price that cannot be had now is a later
    run's. How many cards were written."""
    now = now or datetime.now(UTC)
    books, implied = await _books(session, company_id)
    if not books:
        return 0
    held_cusips = sorted({h.cusip for qs in books.values() for q in qs for h in q.held})
    symbols = await cusips.symbols(session, held_cusips)
    prices = Prices(implied, symbols, await _closes(session, set(symbols.values())))
    prices.asked = set(
        (
            await session.execute(
                select(PriceAsk.symbol, PriceAsk.start, PriceAsk.end).where(
                    PriceAsk.asked_at > now - RETRY
                )
            )
        ).tuples()
    )

    # 1. the latest quotes the latest stretches want: the kept ones, and those missing or old
    fetched_at: dict[str, datetime] = {}
    for row in (await session.scalars(select(StockQuote))).all():
        prices.quotes[row.symbol] = Quote(row.price, row.day)
        fetched_at[row.symbol] = row.fetched_at
    for quarters in books.values():
        simulate(quarters, prices, today)
    if quote is not None:
        due = sorted(
            (s for s in prices.quoted if s not in fetched_at or fetched_at[s] < now - QUOTE_AGE),
            key=lambda s: (s in fetched_at, fetched_at.get(s, now), s),
        )
        for i, symbol in enumerate(due[:quotes_per_run]):
            if i:
                await asyncio.sleep(quote_pause)
            try:
                got = await quote(symbol)
            except Exception as error:  # noqa: BLE001 — one quote missing is a later run's
                log.warning("portfolios: no quote for %s: %s", symbol, type(error).__name__)
                continue
            if got is None:
                continue
            prices.quotes[symbol] = got
            statement = insert(StockQuote).values(
                symbol=symbol, price=got.price, day=got.day, fetched_at=now
            )
            await session.execute(
                statement.on_conflict_do_update(
                    index_elements=["symbol"],
                    set_={"price": got.price, "day": got.day, "fetched_at": now},
                )
            )

    # 2. what only Tiingo can tell, now that the quotes are known
    prices.needs.clear()
    for quarters in books.values():
        simulate(quarters, prices, today)
    if tiingo is not None:
        wanted = sorted(prices.needs.items(), key=lambda item: (-item[1], item[0][0]))
        for i, ((symbol, start, end), _) in enumerate(wanted[:tiingo_per_run]):
            if i:
                await asyncio.sleep(tiingo_pause)
            try:
                rows = await tiingo(
                    TIINGO_DAILY.format(symbol=tiingo_symbol(symbol)),
                    {
                        "startDate": (start - STALE).isoformat(),
                        "endDate": (end or today).isoformat(),
                    },
                )
            except Exception as error:  # noqa: BLE001 — a stretch missing is next run's
                log.warning("portfolios: %s not read: %s", symbol, type(error).__name__)
                continue
            fetched = parse_closes(rows)
            await _keep_closes(session, symbol, fetched)
            merged = {c.day: c for c in prices.closes.get(symbol, [])}
            merged.update({c.day: c for c in fetched})
            prices.closes[symbol] = [merged[d] for d in sorted(merged)]
            # asked: what it could not answer is not asked again for a while (the latest stretch's
            # end is its quote's day, so a new day's quote may ask again)
            asked = (symbol, start, end or prices.quotes[symbol].day)
            prices.asked.add(asked)
            statement = insert(PriceAsk).values(
                symbol=asked[0], start=asked[1], end=asked[2], asked_at=now
            )
            await session.execute(
                statement.on_conflict_do_update(
                    index_elements=["symbol", "start", "end"], set_={"asked_at": now}
                )
            )

    # 3. the cards (asking once more, only to count what is still waiting for Tiingo)
    written = 0
    for source_id, quarters in books.items():
        ordered = sorted(quarters, key=lambda q: q.period)
        latest, previous = ordered[-1], (ordered[-2] if len(ordered) > 1 else None)
        result = simulate(quarters, prices, today)
        card = {
            "company_id": company_id,
            "period": latest.period,
            "filed": latest.filed,
            "long_value_usd": latest.value,
            "holdings": [
                {
                    "cusip": t.cusip,
                    "symbol": symbols.get(t.cusip),
                    "issuer": t.issuer,
                    "value_usd": t.value,
                    "weight": float(round(t.weight, 6)),
                }
                for t in largest(latest)
            ],
            "moves": [
                {
                    "cusip": m.cusip,
                    "symbol": symbols.get(m.cusip),
                    "issuer": m.issuer,
                    "change": m.change,
                    "shares": m.shares,
                    "previous_shares": m.previous_shares,
                    "value_change_usd": m.value_change,
                }
                for m in moves(latest, previous, prices)
            ],
            "return_pct": round(result.growth, 6) if result.growth is not None else None,
            "return_start": result.start,
            "return_through": result.through,
            "coverage": round(result.coverage, 4) if result.coverage is not None else None,
            "pending": result.pending,
            "computed_at": now,
        }
        statement = insert(PortfolioStat).values(source_id=source_id, **card)
        await session.execute(
            statement.on_conflict_do_update(index_elements=["source_id"], set_=card)
        )
        written += 1
    await session.flush()
    return written


class PortfolioKeeper:
    def __init__(
        self,
        quote: GetQuote | None,
        tiingo: GetRows | None,
        *,
        quote_pause: float = QUOTE_PAUSE,
        tiingo_pause: float = TIINGO_PAUSE,
    ) -> None:
        self.quote = quote
        """Finnhub's quotes; None offline or without its key: no return is given."""
        self.tiingo = tiingo
        """Tiingo's closes; None offline or without its key: only what the 13Fs price."""
        self.quote_pause = quote_pause
        self.tiingo_pause = tiingo_pause

    def schedule_handler(self) -> Handler:
        """The ``newsroom.refresh_portfolio_stats`` handler."""

        async def handler(
            session: AsyncSession, schedule: Schedule, scheduled_for: datetime
        ) -> None:
            await refresh_portfolio_stats(
                session,
                schedule.company_id,
                quote=self.quote,
                tiingo=self.tiingo,
                today=datetime.now(UTC).date(),
                quote_pause=self.quote_pause,
                tiingo_pause=self.tiingo_pause,
            )

        return handler
