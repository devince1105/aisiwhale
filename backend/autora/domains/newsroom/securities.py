"""Any Taiwan or US stock (D-061): the lists to look one up in, and which ones readers want.

The twenty stocks on the market strip have always had pages (``holdings.STOCKS``, with their
13F CUSIPs and aliases). Everything else listed is here, refreshed once a day from each market's
own list:

- **TWSE** (上市): ``STOCK_DAY_ALL`` has every security traded that day, stocks and ETFs, with
  its Chinese name; ``t187ap03_L`` adds a company's English short name.
- **TPEx** (上櫃): its daily close list, kept to stocks (four digits) and ETFs (``00…``) — the
  rest are warrants and bonds.
- **US**: Finnhub's symbol list, kept to common stocks, ETFs and ADRs on the main exchanges
  (Nasdaq, NYSE, NYSE Arca, Cboe BZX, NYSE American); OTC and warrants left out.

A stock somebody asks about — puts on a watchlist, or opens its page — is **tracked**: its daily
prices are fetched and kept while it is asked about (``price_history``). Whose request it was is
not kept here.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import case, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from autora.db.models import Schedule
from autora.domains.newsroom.holdings import STOCKS, Stock
from autora.domains.newsroom.models import Security, TrackedSecurity
from autora.runtime.scheduler import Handler

log = logging.getLogger(__name__)

SECURITIES_SCHEDULE = "newsroom.refresh_securities"
SECURITIES_CRON = "10 23 * * *"
"""07:10 in Taipei: after both markets' lists for the day before are out."""

TWSE_ALL = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
TWSE_COMPANIES = "https://openapi.twse.com.tw/v1/opendata/t187ap03_L"
TPEX_ALL = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes"
FINNHUB_SYMBOLS = "https://finnhub.io/api/v1/stock/symbol"

US_EXCHANGES = {"XNAS", "XNYS", "ARCX", "BATS", "XASE"}
US_KINDS = {"Common Stock": "stock", "ETP": "etf", "ADR": "adr"}
TRACKED_FOR = timedelta(days=30)
"""How long a stock nobody asks about again keeps being refreshed."""

TW_CODE = re.compile(r"^(\d{4}|00\d{3,4}[A-Z]?)$")
"""A Taiwan stock (four digits) or ETF (00…, a letter for leveraged or bond funds)."""
US_SYMBOL = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")


def market_of(symbol: str) -> str | None:
    """Which market a symbol belongs to, from its shape: digits are Taiwan's, letters the US."""
    symbol = symbol.upper()
    if TW_CODE.match(symbol):
        return "tw"
    if US_SYMBOL.match(symbol):
        return "us"
    return None


@dataclass(frozen=True)
class Listed:
    market: str
    symbol: str
    name: str
    name_en: str | None
    exchange: str
    kind: str


def twse_listed(everything: list[dict], companies: list[dict]) -> list[Listed]:
    english = {
        row.get("公司代號"): (row.get("英文簡稱") or "").strip() or None for row in companies
    }
    out = []
    for row in everything:
        code, name = str(row.get("Code", "")).strip(), str(row.get("Name", "")).strip()
        if TW_CODE.match(code) and name:
            kind = "etf" if code.startswith("00") else "stock"
            out.append(Listed("tw", code, name, english.get(code), "TWSE", kind))
    return out


def tpex_listed(everything: list[dict]) -> list[Listed]:
    out = []
    for row in everything:
        code = str(row.get("SecuritiesCompanyCode", "")).strip()
        name = str(row.get("CompanyName", "")).strip()
        if TW_CODE.match(code) and name:
            kind = "etf" if code.startswith("00") else "stock"
            out.append(Listed("tw", code, name, None, "TPEx", kind))
    return out


def us_listed(symbols: list[dict]) -> list[Listed]:
    out = []
    for row in symbols:
        symbol = str(row.get("symbol", "")).strip().upper()
        kind = US_KINDS.get(str(row.get("type", "")))
        if kind and row.get("mic") in US_EXCHANGES and US_SYMBOL.match(symbol):
            name = str(row.get("description", "")).strip() or symbol
            out.append(Listed("us", symbol, name, None, str(row["mic"]), kind))
    return out


async def store(session: AsyncSession, listed: list[Listed]) -> int:
    """Upsert the lists; a security no longer listed is kept (its page, its history)."""
    by_key = {(item.market, item.symbol): item for item in listed}  # a symbol listed twice: once
    rows = [
        {
            "market": i.market,
            "symbol": i.symbol,
            "name": i.name,
            "name_en": i.name_en,
            "exchange": i.exchange,
            "kind": i.kind,
        }
        for i in by_key.values()
    ]
    for start in range(0, len(rows), 1000):
        statement = insert(Security).values(rows[start : start + 1000])
        await session.execute(
            statement.on_conflict_do_update(
                index_elements=["market", "symbol"],
                set_={
                    name: statement.excluded[name]
                    for name in ("name", "name_en", "exchange", "kind")
                }
                | {"updated_at": func.now()},
            )
        )
    return len(rows)


GetJson = Callable[[str, dict, dict], Awaitable[object]]
"""(url, params, headers) -> the parsed JSON answer."""


async def refresh_securities(
    session: AsyncSession, get: GetJson, *, finnhub_key: str | None
) -> dict[str, int]:
    """Each market's list, again. A market that does not answer keeps yesterday's."""
    counts: dict[str, int] = {}

    async def attempt(name: str, load: Callable[[], Awaitable[list[Listed]]]) -> None:
        try:
            counts[name] = await store(session, await load())
            await session.commit()
        except Exception as error:  # noqa: BLE001 — the others go on
            await session.rollback()
            log.warning("securities: %s not refreshed: %s", name, type(error).__name__)

    async def twse() -> list[Listed]:
        return twse_listed(await get(TWSE_ALL, {}, {}), await get(TWSE_COMPANIES, {}, {}))

    async def tpex() -> list[Listed]:
        return tpex_listed(await get(TPEX_ALL, {}, {}))

    async def us() -> list[Listed]:
        # the key in a header: the list comes back as a redirect to a signed file
        headers = {"X-Finnhub-Token": finnhub_key or ""}
        return us_listed(await get(FINNHUB_SYMBOLS, {"exchange": "US"}, headers))

    await attempt("twse", twse)
    await attempt("tpex", tpex)
    if finnhub_key:
        await attempt("us", us)
    return counts


def http_json(timeout: float = 60.0) -> GetJson:
    import httpx

    async def get(url: str, params: dict, headers: dict) -> object:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            return (await client.get(url, params=params, headers=headers)).raise_for_status().json()

    return get


async def no_securities(url: str, params: dict, headers: dict) -> object:
    """Offline (fixtures, tests): every list is empty, and nothing is asked of anybody."""
    return []


class SecuritiesKeeper:
    def __init__(self, get: GetJson, finnhub_key: str | None) -> None:
        self.get = get
        self.finnhub_key = finnhub_key

    def schedule_handler(self) -> Handler:
        async def handler(
            session: AsyncSession, schedule: Schedule, scheduled_for: datetime
        ) -> None:
            await refresh_securities(session, self.get, finnhub_key=self.finnhub_key)

        return handler


# --- looking one up -----------------------------------------------------------------------------


def as_stock(security: Security) -> Stock:
    """A listed security as a stock page reads one: no CUSIPs, so no 13F holders to show."""
    english = security.name_en or security.name
    return Stock(
        security.symbol, security.market, security.name, english, exchange=security.exchange
    )


async def find(session: AsyncSession, symbol: str) -> Stock | None:
    """The stock a page's symbol names: one of the strip's twenty, or any listed security."""
    symbol = symbol.upper()
    if (curated := STOCKS.get(symbol)) is not None:
        return curated
    market = market_of(symbol)
    if market is None:
        return None
    security = await session.scalar(
        select(Security).where(Security.market == market, Security.symbol == symbol)
    )
    return as_stock(security) if security else None


async def search(session: AsyncSession, query: str, *, limit: int = 12) -> list[Security]:
    """By code or ticker (from its start) or by name (anywhere in it): an exact symbol first,
    then symbols starting with it, then names; stocks before funds, shorter names first."""
    q = query.strip()
    if not q:
        return []
    upper = q.upper()
    pattern = f"%{q.replace('%', '').replace('_', '')}%"
    rank = case(
        (Security.symbol == upper, 0),
        (Security.symbol.startswith(upper), 1),
        else_=2,
    )
    rows = await session.scalars(
        select(Security)
        .where(
            or_(
                Security.symbol.startswith(upper),
                Security.name.ilike(pattern),
                Security.name_en.ilike(pattern),
            )
        )
        .order_by(
            rank,
            case((Security.kind == "stock", 0), else_=1),
            func.length(Security.name),
            Security.symbol,
        )
        .limit(limit)
    )
    return list(rows)


async def track(session: AsyncSession, stock: Stock, *, now: datetime | None = None) -> None:
    """Somebody asked about this stock: keep its prices fresh for another ``TRACKED_FOR``."""
    now = now or datetime.now(UTC)
    statement = insert(TrackedSecurity).values(
        market=stock.market, symbol=stock.symbol, last_requested_at=now
    )
    await session.execute(
        statement.on_conflict_do_update(
            index_elements=["market", "symbol"], set_={"last_requested_at": now}
        )
    )


async def tracked(session: AsyncSession, market: str, *, now: datetime | None = None) -> list[str]:
    """The symbols of one market somebody asked about lately, besides the strip's own."""
    since = (now or datetime.now(UTC)) - TRACKED_FOR
    rows = await session.scalars(
        select(TrackedSecurity.symbol)
        .where(TrackedSecurity.market == market, TrackedSecurity.last_requested_at >= since)
        .order_by(TrackedSecurity.symbol)
    )
    return list(rows)


async def exchange_of(session: AsyncSession, symbols: list[str]) -> dict[str, str]:
    """Where each Taiwan symbol is listed (TWSE or TPEx): its history is asked of that one."""
    if not symbols:
        return {}
    rows = await session.execute(
        select(Security.symbol, Security.exchange).where(
            Security.market == "tw", Security.symbol.in_(symbols)
        )
    )
    return dict(rows.all())
