"""Daily prices for the stock pages' charts (D-059): Taiwan's from the exchange itself.

TWSE's STOCK_DAY answers one stock's one month at a time, dates in the Republic of China
calendar ("115/09/01" is 2026-09-01) and numbers with thousands separators; a day with no trade
shows "--". A stock's history reaches five years back (``HISTORY_MONTHS``): the first refresh
fills it, every later one only the months since its last stored day — and, if the history is
shorter than five years (it was two before D-059's follow-up), the months before its first,
walking back until a month has no trades (the stock was not listed yet). TWSE refuses a
client that asks too quickly, so requests are spaced (``pause``): a first fill of seven stocks is
about 175 requests, some minutes of the worker's time, once.

The United States comes from Tiingo (the user's choice; its key in a header, never in a URL).
One request gives a stock's whole five years, split- and dividend-adjusted, so every refresh asks
for all of it again: a split rewrites the past, and thirteen requests twice a day is well inside
the free plan's 1,000 a day. Without the key a US page has no chart.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from autora.db.models import Schedule
from autora.domains.newsroom.market_strip import TW_STOCKS, US_STOCKS
from autora.domains.newsroom.models import PriceBar
from autora.runtime.scheduler import Handler

log = logging.getLogger(__name__)

PRICES_SCHEDULE = "newsroom.refresh_prices"
PRICES_CRON = "20 7,10 * * 1-5"
"""15:20 and 18:20 in Taipei, weekdays: after TWSE publishes the day, and once more in case."""

TWSE_DAY = "https://www.twse.com.tw/exchangeReport/STOCK_DAY"
HISTORY_MONTHS = 60
"""Five years: a monthly chart with its 60-month average, and room for the yearly one."""
PAUSE_SECONDS = 2.5
"""Between two TWSE requests: it answers a burst with a block, not with data."""


@dataclass(frozen=True)
class Bar:
    day: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int


class PriceError(Exception):
    pass


def _number(text: str) -> Decimal:
    return Decimal(text.replace(",", "").strip())


def _roc_day(text: str) -> date:
    year, month, day = (int(part) for part in text.strip().split("/"))
    return date(year + 1911, month, day)


COLUMNS = ("日期", "成交股數", "開盤價", "最高價", "最低價", "收盤價")


def parse_twse_month(payload: dict) -> list[Bar]:
    """One month of STOCK_DAY. A day without a trade ("--") is left out, not drawn as zero."""
    if payload.get("stat") != "OK":
        if "沒有符合條件" in str(payload.get("stat")):  # no data for that month: not an error
            return []
        raise PriceError(f"TWSE answered {payload.get('stat')!r}")
    fields = payload.get("fields") or []
    try:
        at = {name: fields.index(name) for name in COLUMNS}
    except ValueError as error:
        raise PriceError(f"TWSE's columns changed: {fields}") from error
    bars = []
    for row in payload.get("data") or []:
        try:
            bars.append(
                Bar(
                    day=_roc_day(row[at["日期"]]),
                    open=_number(row[at["開盤價"]]),
                    high=_number(row[at["最高價"]]),
                    low=_number(row[at["最低價"]]),
                    close=_number(row[at["收盤價"]]),
                    volume=int(_number(row[at["成交股數"]])),
                )
            )
        except (InvalidOperation, ValueError, IndexError):
            continue  # "--": no trade that day
    return bars


def months_between(first: date, last: date) -> list[date]:
    """The first day of every month from ``first``'s to ``last``'s, in order."""
    months, year, month = [], first.year, first.month
    while (year, month) <= (last.year, last.month):
        months.append(date(year, month, 1))
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return months


def _months_back(today: date, count: int) -> date:
    year, month = today.year, today.month - (count - 1)
    while month < 1:
        year, month = year - 1, month + 12
    return date(year, month, 1)


GetJson = Callable[[str, dict], Awaitable[dict]]


async def refresh_tw(
    session: AsyncSession,
    get: GetJson,
    *,
    today: date,
    symbols: tuple[str, ...] = TW_STOCKS,
    pause: float = PAUSE_SECONDS,
) -> int:
    """Bring every Taiwan stock's bars up to ``today``. How many bars were written."""
    written, requests = 0, 0

    async def month_of(symbol: str, month: date) -> list[Bar] | None:
        """One month's bars; None when it could not be read (next time's)."""
        nonlocal requests
        if requests:
            await asyncio.sleep(pause)
        requests += 1
        try:
            payload = await get(
                TWSE_DAY, {"response": "json", "date": month.strftime("%Y%m01"), "stockNo": symbol}
            )
            return parse_twse_month(payload)
        except Exception as error:  # noqa: BLE001 — one month missing is next time's
            log.warning("prices: %s %s not read: %s", symbol, f"{month:%Y-%m}", error)
            return None

    horizon = _months_back(today, HISTORY_MONTHS)
    for symbol in symbols:
        first, last = (
            await session.execute(
                select(func.min(PriceBar.day), func.max(PriceBar.day)).where(
                    PriceBar.market == "tw", PriceBar.symbol == symbol
                )
            )
        ).one()
        for month in months_between(last or horizon, today):
            bars = await month_of(symbol, month)
            written += await _store(session, "tw", symbol, bars or [], source="TWSE")
        # the years before the first stored month, newest first, until the stock had no trades
        if first is not None and first.replace(day=1) > horizon:
            for month in reversed(months_between(horizon, first.replace(day=1))[:-1]):
                bars = await month_of(symbol, month)
                if bars == []:
                    break  # not listed yet: nothing older either
                written += await _store(session, "tw", symbol, bars or [], source="TWSE")
        await session.commit()  # a stock at a time: an interrupted first fill keeps its progress
    return written


TIINGO_DAILY = "https://api.tiingo.com/tiingo/daily/{symbol}/prices"


def parse_tiingo(rows: list[dict]) -> list[Bar]:
    """Tiingo's daily rows, adjusted for splits and dividends, as bars."""
    bars = []
    for row in rows:
        try:
            bars.append(
                Bar(
                    day=date.fromisoformat(str(row["date"])[:10]),
                    open=Decimal(str(row["adjOpen"])),
                    high=Decimal(str(row["adjHigh"])),
                    low=Decimal(str(row["adjLow"])),
                    close=Decimal(str(row["adjClose"])),
                    volume=int(row["adjVolume"]),
                )
            )
        except (KeyError, TypeError, ValueError, InvalidOperation):
            continue
    return bars


GetRows = Callable[[str, dict], Awaitable[list[dict]]]


async def refresh_us(
    session: AsyncSession,
    get: GetRows,
    *,
    today: date,
    symbols: tuple[str, ...] = US_STOCKS,
    pause: float = 1.0,
) -> int:
    """Every US stock's last five years, again (a split rewrites them). Bars written."""
    start = _months_back(today, HISTORY_MONTHS)
    written = 0
    for number, symbol in enumerate(symbols):
        if number:
            await asyncio.sleep(pause)
        try:
            rows = await get(
                TIINGO_DAILY.format(symbol=symbol),
                {"startDate": start.isoformat(), "endDate": today.isoformat()},
            )
        except Exception as error:  # noqa: BLE001 — one stock missing is next time's
            log.warning("prices: %s not read: %s", symbol, _describe(error))
            continue
        written += await _store(session, "us", symbol, parse_tiingo(rows), source="Tiingo")
        await session.commit()
    return written


def _describe(error: Exception) -> str:
    """An error without anything a URL or header could carry (the key is in a header)."""
    status = getattr(getattr(error, "response", None), "status_code", None)
    return f"{type(error).__name__}{f' (HTTP {status})' if status else ''}"


async def _store(
    session: AsyncSession, market: str, symbol: str, bars: list[Bar], *, source: str
) -> int:
    if not bars:
        return 0
    rows = [
        {
            "market": market,
            "symbol": symbol,
            "day": b.day,
            "open": b.open,
            "high": b.high,
            "low": b.low,
            "close": b.close,
            "volume": b.volume,
            "source": source,
        }
        for b in bars
    ]
    statement = insert(PriceBar).values(rows)
    await session.execute(
        statement.on_conflict_do_update(
            index_elements=["market", "symbol", "day"],
            set_={
                name: statement.excluded[name]
                for name in ("open", "high", "low", "close", "volume", "source")
            },
        )
    )
    return len(rows)


class PricesKeeper:
    def __init__(
        self, get: GetJson, us: GetRows | None = None, *, pause: float = PAUSE_SECONDS
    ) -> None:
        self.get = get
        self.pause = pause
        """Between two TWSE requests; 0 when nothing is asked of TWSE (offline)."""
        self.us = us
        """Tiingo's reader; None without its key, and the US pages have no chart."""

    def schedule_handler(self) -> Handler:
        """The ``newsroom.refresh_prices`` handler."""

        async def handler(
            session: AsyncSession, schedule: Schedule, scheduled_for: datetime
        ) -> None:
            today = datetime.now(UTC).date()
            await refresh_tw(session, self.get, today=today, pause=self.pause)
            if self.us is not None:
                await refresh_us(session, self.us, today=today)

        return handler


async def no_prices(url: str, params: dict) -> dict:
    """Offline (fixtures, tests): every month is empty, and nothing is asked of the exchange."""
    return {"stat": "OK", "fields": list(COLUMNS), "data": []}


def http_json(timeout: float = 20.0) -> GetJson:
    import httpx

    async def get(url: str, params: dict) -> dict:
        async with httpx.AsyncClient(timeout=timeout) as client:
            return (await client.get(url, params=params)).raise_for_status().json()

    return get


def tiingo_rows(api_key: str, timeout: float = 20.0) -> GetRows:
    import httpx

    headers = {"Authorization": f"Token {api_key}", "Content-Type": "application/json"}

    async def get(url: str, params: dict) -> list[dict]:
        async with httpx.AsyncClient(timeout=timeout, headers=headers) as client:
            return (await client.get(url, params=params)).raise_for_status().json()

    return get


# --- what a stock page reads --------------------------------------------------------------------


class PublicBar(BaseModel):
    d: date
    o: float
    h: float
    l: float  # noqa: E741 — the chart's own short names
    c: float
    v: int


class PublicHistory(BaseModel):
    symbol: str
    market: str
    source: str | None
    bars: list[PublicBar]
    """Oldest first, every stored trading day (about five years)."""


DAILY_LIMIT = 0.10
"""TWSE's price limit: no stock closes more than 10% from the day before, except across a split."""


def split_factors(bars: list[PublicBar]) -> list[float]:
    """For each bar, what its prices are divided by to read on today's shares.

    TWSE's figures are not adjusted: 0050's 1-for-4 split of 2025-06-18 is a 74.8% fall from
    one close to the next. A move past the daily limit whose ratio is a whole number (2, 4, 10…
    or, for a reverse split, its inverse) can only be a split; every bar before it is scaled.
    A capital reduction or a listing's first day moves by a ratio that is not whole, and is left
    as it is."""
    factors = [1.0] * len(bars)
    for i in range(len(bars) - 1, 0, -1):
        before, after = bars[i - 1].c, bars[i].c
        if not before or not after or abs(after / before - 1) <= DAILY_LIMIT + 0.005:
            continue
        ratio = before / after
        whole = round(ratio) if ratio >= 1 else 1 / round(1 / ratio)
        if (ratio >= 1.9 or ratio <= 1 / 1.9) and abs(ratio / whole - 1) <= DAILY_LIMIT:
            for j in range(i):
                factors[j] *= whole
    return factors


async def history(session: AsyncSession, market: str, symbol: str) -> PublicHistory:
    """Oldest first; a Taiwan stock's split-adjusted (Tiingo's already are)."""
    rows = (
        await session.scalars(
            select(PriceBar)
            .where(PriceBar.market == market, PriceBar.symbol == symbol)
            .order_by(PriceBar.day)
        )
    ).all()
    bars = [
        PublicBar(
            d=r.day,
            o=float(r.open),
            h=float(r.high),
            l=float(r.low),
            c=float(r.close),
            v=int(r.volume),
        )  # fmt: skip
        for r in rows
    ]
    if market == "tw":
        bars = [
            PublicBar(
                d=b.d,
                o=round(b.o / f, 4),
                h=round(b.h / f, 4),
                l=round(b.l / f, 4),
                c=round(b.c / f, 4),
                v=round(b.v * f),
            )  # fmt: skip
            for b, f in zip(bars, split_factors(bars), strict=True)
        ]
    return PublicHistory(
        symbol=symbol, market=market, source=rows[-1].source if rows else None, bars=bars
    )


# --- a US stock's last days, in 15-minute bars (D-059) -------------------------------------------

TIINGO_IEX = "https://api.tiingo.com/iex/{symbol}/prices"
INTRADAY_DAYS = 5
"""Trading days of 15-minute bars: a week's moves within the day, about 130 bars."""
INTRADAY_TTL_SECONDS = 600.0
"""Tiingo's free plan allows 50 requests an hour: a stock's bars are asked for at most every ten
minutes, however many readers open its page."""


class PublicIntradayBar(BaseModel):
    t: datetime
    """The bar's start, UTC."""
    o: float
    h: float
    l: float  # noqa: E741
    c: float
    v: int
    """IEX's volume only: a fraction of the whole market's."""


class PublicIntraday(BaseModel):
    symbol: str
    source: str | None
    bars: list[PublicIntradayBar]


def parse_iex(rows: list[dict], days: int = INTRADAY_DAYS) -> list[PublicIntradayBar]:
    """Tiingo's IEX bars, the last ``days`` trading days of them, oldest first."""
    bars = []
    for row in rows:
        try:
            bars.append(
                PublicIntradayBar(
                    t=datetime.fromisoformat(str(row["date"]).replace("Z", "+00:00")),
                    o=float(row["open"]),
                    h=float(row["high"]),
                    l=float(row["low"]),
                    c=float(row["close"]),
                    v=int(row.get("volume") or 0),
                )  # fmt: skip
            )
        except (KeyError, TypeError, ValueError):
            continue
    bars.sort(key=lambda b: b.t)
    kept = sorted({b.t.date() for b in bars})[-days:]
    return [b for b in bars if b.t.date() in kept]


class IntradayCache:
    """Each US stock's 15-minute bars, kept ``ttl`` seconds (the free plan's hourly limit)."""

    def __init__(self, get: GetRows | None, *, ttl: float = INTRADAY_TTL_SECONDS, clock=None):
        self.get = get
        self.ttl = ttl
        self.clock = clock or (lambda: datetime.now(UTC))
        self._kept: dict[str, tuple[datetime, PublicIntraday]] = {}
        self._lock = asyncio.Lock()

    async def bars(self, symbol: str) -> PublicIntraday:
        if self.get is None:
            return PublicIntraday(symbol=symbol, source=None, bars=[])
        async with self._lock:  # one reader asks Tiingo; the others get what it got
            now = self.clock()
            kept = self._kept.get(symbol)
            if kept and (now - kept[0]).total_seconds() < self.ttl:
                return kept[1]
            try:
                rows = await self.get(
                    TIINGO_IEX.format(symbol=symbol),
                    {
                        "startDate": (
                            now.date() - timedelta(days=INTRADAY_DAYS * 2 + 4)
                        ).isoformat(),
                        "resampleFreq": "15min",
                        "columns": "open,high,low,close,volume",
                    },
                )
                answer = PublicIntraday(symbol=symbol, source="Tiingo IEX", bars=parse_iex(rows))
            except Exception as error:  # noqa: BLE001 — a page without its intraday chart
                log.warning("intraday: %s not read: %s", symbol, _describe(error))
                return kept[1] if kept else PublicIntraday(symbol=symbol, source=None, bars=[])
            self._kept[symbol] = (now, answer)
            return answer
