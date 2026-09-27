"""Daily prices for the stock pages' charts (D-059): Taiwan's from the exchange itself.

TWSE's STOCK_DAY answers one stock's one month at a time, dates in the Republic of China
calendar ("115/09/01" is 2026-09-01) and numbers with thousands separators; a day with no trade
shows "--". The first refresh of a stock fills two years — enough for a 250-day average from the
first day shown — and every later one only the months since its last stored day. TWSE refuses a
client that asks too quickly, so requests are spaced (``pause``): a first fill of seven stocks is
about 175 requests, some minutes of the worker's time, once.

The United States comes from Tiingo (the user's choice; its key in a header, never in a URL).
One request gives a stock's whole two years, split- and dividend-adjusted, so every refresh asks
for all of it again: a split rewrites the past, and thirteen requests twice a day is well inside
the free plan's 1,000 a day. Without the key a US page has no chart.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
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
FIRST_FILL_MONTHS = 24
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
    written, first_request = 0, True
    for symbol in symbols:
        last = await session.scalar(
            select(func.max(PriceBar.day)).where(PriceBar.market == "tw", PriceBar.symbol == symbol)
        )
        start = last or _months_back(today, FIRST_FILL_MONTHS)
        for month in months_between(start, today):
            if not first_request:
                await asyncio.sleep(pause)
            first_request = False
            try:
                payload = await get(
                    TWSE_DAY,
                    {"response": "json", "date": month.strftime("%Y%m01"), "stockNo": symbol},
                )
                bars = parse_twse_month(payload)
            except Exception as error:  # noqa: BLE001 — one month missing is next time's
                log.warning("prices: %s %s not read: %s", symbol, f"{month:%Y-%m}", error)
                continue
            written += await _store(session, "tw", symbol, bars, source="TWSE")
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
    """Every US stock's last two years, again (a split rewrites them). Bars written."""
    start = _months_back(today, FIRST_FILL_MONTHS)
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
    def __init__(self, get: GetJson, us: GetRows | None = None) -> None:
        self.get = get
        self.us = us
        """Tiingo's reader; None without its key, and the US pages have no chart."""

    def schedule_handler(self) -> Handler:
        """The ``newsroom.refresh_prices`` handler."""

        async def handler(
            session: AsyncSession, schedule: Schedule, scheduled_for: datetime
        ) -> None:
            today = datetime.now(UTC).date()
            await refresh_tw(session, self.get, today=today)
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
    """Oldest first, every stored trading day (about two years)."""


async def history(session: AsyncSession, market: str, symbol: str) -> PublicHistory:
    rows = (
        await session.scalars(
            select(PriceBar)
            .where(PriceBar.market == market, PriceBar.symbol == symbol)
            .order_by(PriceBar.day)
        )
    ).all()
    return PublicHistory(
        symbol=symbol,
        market=market,
        source=rows[-1].source if rows else None,
        bars=[
            PublicBar(
                d=r.day,
                o=float(r.open),
                h=float(r.high),
                l=float(r.low),
                c=float(r.close),
                v=int(r.volume),
            )  # fmt: skip
            for r in rows
        ],
    )
