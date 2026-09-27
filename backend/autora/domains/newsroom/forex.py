"""Spot gold and currencies against the New Taiwan dollar (D-072), from Tiingo's forex prices —
the key the stock charts use (D-059) — kept once for the market strip, the watchlist's charts and
gold's price a gram.

Tiingo's free plan allows 50 requests an hour for everything the key does, stock charts
included, so every pair is asked for at most once every ``KEEP``, whoever wants it: five years of
days in one request. Tiingo quotes the dollar against the New Taiwan dollar (``usdtwd``) and
against most currencies, but no other currency against the New Taiwan dollar: yen to NT$ is
worked out each day as ``usdtwd`` over ``usdjpy``. Only a day's close can be worked out that way
— a cross rate's high and low are not the two pairs' — so such a chart is of closes.

What it was given is kept in the database too (D-082): bars in ``price_bars`` (market ``fx`` or
``crypto``), when each series was asked for in ``price_fetches``. A restart reads them back and
asks Tiingo only for a series whose ``KEEP`` (or ``RETRY``) has run out — before, every restart
asked for every pair at once, and a few in an hour ran through the allowance.

Gold and currencies trade again from Sunday evening (UTC), Monday morning in Taipei; Tiingo gives
that a Sunday bar, which is folded into the Monday after (a weekend with no trading yet is left
out).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from autora.domains.newsroom.models import PriceBar, PriceFetch
from autora.domains.newsroom.price_history import Bar, GetRows, PublicBar, _store

log = logging.getLogger(__name__)

TIINGO_FX = "https://api.tiingo.com/tiingo/fx/{pair}/prices"
TIINGO_CRYPTO = "https://api.tiingo.com/tiingo/crypto/prices"
SOURCE = "Tiingo"
YEARS = 5
KEEP = timedelta(hours=3)
"""How long one answer for a pair serves everybody: a day's bar moves until the day is done."""
RETRY = timedelta(minutes=30)
EARLIEST = datetime.min.replace(tzinfo=UTC)

Sessions = Callable[[], AbstractAsyncContextManager[AsyncSession]]

CURRENCIES: tuple[tuple[str, str, str], ...] = (
    ("USD", "美金", "US dollar"),
    ("HKD", "港幣", "Hong Kong dollar"),
    ("GBP", "英鎊", "British pound"),
    ("AUD", "澳幣", "Australian dollar"),
    ("CAD", "加拿大幣", "Canadian dollar"),
    ("SGD", "新加坡幣", "Singapore dollar"),
    ("CHF", "瑞士法郎", "Swiss franc"),
    ("JPY", "日圓", "Japanese yen"),
    ("ZAR", "南非幣", "South African rand"),
    ("SEK", "瑞典幣", "Swedish krona"),
    ("NZD", "紐元", "New Zealand dollar"),
    ("THB", "泰幣", "Thai baht"),
    ("PHP", "菲國比索", "Philippine peso"),
    ("IDR", "印尼幣", "Indonesian rupiah"),
    ("EUR", "歐元", "Euro"),
    ("KRW", "韓元", "South Korean won"),
    ("VND", "越南盾", "Vietnamese dong"),
    ("MYR", "馬來幣", "Malaysian ringgit"),
    ("CNY", "人民幣", "Chinese yuan"),
)
"""Bank of Taiwan's posted currencies (rate.bot.com.tw, 2026-09-27), in its order and with its
names: what 外匯 covers (D-067)."""

PAIRS: dict[str, tuple[str, bool]] = {
    "HKD": ("usdhkd", True),
    "GBP": ("gbpusd", False),
    "AUD": ("audusd", False),
    "CAD": ("usdcad", True),
    "SGD": ("usdsgd", True),
    "CHF": ("usdchf", True),
    "JPY": ("usdjpy", True),
    "ZAR": ("usdzar", True),
    "SEK": ("usdsek", True),
    "NZD": ("nzdusd", False),
    "PHP": ("usdphp", True),
    "IDR": ("usdidr", True),
    "EUR": ("eurusd", False),
    "KRW": ("usdkrw", True),
    "CNY": ("usdcny", True),
}
"""Each currency's pair against the dollar as Tiingo quotes it (checked 2026-09-27), and whether
it is dollars' worth of it (``usdjpy``: yen a dollar) or its worth in dollars (``eurusd``). Thai
baht Tiingo does not have; the dong and the ringgit went unchecked (the hour's requests had run
out) and are left out until they are."""

CHARTED = ("USD", *PAIRS)
"""The currencies that have a chart against the New Taiwan dollar."""
NAMES = {code: (zh, en) for code, zh, en in CURRENCIES}


def bars_from(rows: list[dict]) -> list[PublicBar]:
    """Tiingo's daily forex rows as one bar a trading day, oldest first (the last row said for a
    day wins); a Sunday's folded into the Monday after, an untraded weekend left out."""
    by_day: dict[date, PublicBar] = {}
    for row in rows:
        try:
            day = datetime.fromisoformat(str(row["date"]).replace("Z", "+00:00")).date()
            bar = PublicBar(d=day, o=row["open"], h=row["high"], l=row["low"], c=row["close"], v=0)
        except (KeyError, TypeError, ValueError):
            continue
        if bar.c > 0:
            by_day[day] = bar
    out: dict[date, PublicBar] = {}
    for day in sorted(by_day):
        bar = by_day[day]
        if day.weekday() >= 5:
            if bar.o == bar.h == bar.l == bar.c:
                continue
            day = day + timedelta(days=7 - day.weekday())
            bar = bar.model_copy(update={"d": day})
        if (kept := out.get(day)) is not None:
            # the Sunday evening that opened this Monday: its open, the day's range, the close
            bar = PublicBar(
                d=day, o=kept.o, h=max(kept.h, bar.h), l=min(kept.l, bar.l), c=bar.c, v=0
            )
        out[day] = bar
    return [out[d] for d in sorted(out)]


def crypto_bars(answer: list) -> list[PublicBar]:
    """Tiingo's crypto answer (one ticker's ``priceData``) as a bar a day, weekends included:
    coins trade every day. Its volume is in coins across exchanges, not shown (``v`` 0)."""
    out: dict[date, PublicBar] = {}
    for row in (answer[0].get("priceData") or []) if answer else []:
        try:
            day = datetime.fromisoformat(str(row["date"]).replace("Z", "+00:00")).date()
            bar = PublicBar(d=day, o=row["open"], h=row["high"], l=row["low"], c=row["close"], v=0)
        except (KeyError, TypeError, ValueError):
            continue
        if bar.c > 0:
            out[day] = bar
    return [out[d] for d in sorted(out)]


def crossed(twd: list[PublicBar], pair: list[PublicBar], per_usd: bool) -> list[PublicBar]:
    """New Taiwan dollars for one unit of a currency, each day both have a close: the dollar's
    NT$ over the currency a dollar buys, or times the dollars the currency buys. Closes only."""
    by_day = {b.d: b.c for b in pair}
    out = []
    for bar in twd:
        other = by_day.get(bar.d)
        if not other:
            continue
        close = bar.c / other if per_usd else bar.c * other
        out.append(PublicBar(d=bar.d, o=close, h=close, l=close, c=close, v=0))
    return out


def _series(name: str) -> tuple[str, str]:
    """A cached name as ``price_bars``' market and symbol: ``crypto:btcusd``, ``usdtwd``."""
    market, _, ticker = name.rpartition(":")
    return (market or "fx"), ticker


class TiingoFx:
    """One per process: each pair asked for once per ``KEEP``, for everybody; the last good
    answer stands when Tiingo does not give one (asked again after ``RETRY``). ``get`` is None
    offline (fixtures, tests) or without Tiingo's key: nothing. With ``sessions`` (D-082) what
    was asked for, and when, is kept in the database and read back by a fresh process; without,
    in memory only."""

    def __init__(
        self,
        get: GetRows | None,
        *,
        sessions: Sessions | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.get = get
        self.sessions = sessions
        self.clock = clock
        self._kept: dict[str, list[PublicBar]] = {}
        self._until: dict[str, datetime] = {}
        self._read: set[str] = set()
        self._lock = asyncio.Lock()

    async def bars(self, pair: str) -> list[PublicBar]:
        """A forex pair's days (``usdtwd``, ``xauusd``)."""
        return await self._cached(
            pair, TIINGO_FX.format(pair=pair), {"resampleFreq": "1day"}, bars_from
        )

    async def crypto(self, ticker: str) -> list[PublicBar]:
        """A coin's days in US dollars (``btcusd``, D-073): every day, weekends too."""
        return await self._cached(
            f"crypto:{ticker}",
            TIINGO_CRYPTO,
            {"tickers": ticker, "resampleFreq": "1day"},
            crypto_bars,
        )

    async def _cached(
        self, name: str, url: str, params: dict, parse: Callable[[list], list[PublicBar]]
    ) -> list[PublicBar]:
        if self.get is None:
            return []
        async with self._lock:
            now = self.clock()
            start = now.date() - timedelta(days=366 * YEARS)
            if name not in self._read:
                self._read.add(name)
                await self._load(name, start)
            if now >= self._until.get(name, EARLIEST):
                fresh: list[PublicBar] = []
                try:
                    fresh = parse(await self.get(url, {"startDate": start.isoformat(), **params}))
                    if not fresh:
                        raise ValueError("no bars")
                    self._kept[name] = fresh
                    self._until[name] = now + KEEP
                except Exception as error:  # noqa: BLE001 — the last good answer stands
                    log.warning("forex: %s not refreshed: %s", name, type(error).__name__)
                    self._until[name] = now + RETRY
                await self._save(name, fresh, now)
        return self._kept.get(name, [])

    async def _load(self, name: str, start: date) -> None:
        """What an earlier process was given, and when it may ask again (D-082)."""
        if self.sessions is None:
            return
        market, symbol = _series(name)
        try:
            async with self.sessions() as session:
                fetch = await session.scalar(
                    select(PriceFetch).where(
                        PriceFetch.market == market, PriceFetch.symbol == symbol
                    )
                )
                if fetch is None:
                    return
                rows = await session.scalars(
                    select(PriceBar)
                    .where(
                        PriceBar.market == market, PriceBar.symbol == symbol, PriceBar.day >= start
                    )
                    .order_by(PriceBar.day)
                )
                bars = [
                    PublicBar(d=r.day, o=r.open, h=r.high, l=r.low, c=r.close, v=0) for r in rows
                ]
        except Exception as error:  # noqa: BLE001 — without the database, Tiingo is asked
            log.warning("forex: %s not read back: %s", name, type(error).__name__)
            return
        if bars:
            self._kept[name] = bars
        self._until[name] = fetch.next_at

    async def _save(self, name: str, fresh: list[PublicBar], now: datetime) -> None:
        """The bars just given (none after a failure), and when to ask again."""
        if self.sessions is None:
            return
        market, symbol = _series(name)

        def number(value: float) -> Decimal:
            return Decimal(str(round(value, 6)))

        bars = [
            Bar(b.d, number(b.o), number(b.h), number(b.l), number(b.c), volume=0) for b in fresh
        ]
        values = {"next_at": self._until[name], **({"fetched_at": now} if fresh else {})}
        try:
            async with self.sessions() as session:
                await _store(session, market, symbol, bars, source=SOURCE)
                statement = insert(PriceFetch).values(market=market, symbol=symbol, **values)
                await session.execute(
                    statement.on_conflict_do_update(
                        index_elements=["market", "symbol"], set_=values
                    )
                )
                await session.commit()
        except Exception as error:  # noqa: BLE001 — kept in memory all the same
            log.warning("forex: %s not stored: %s", name, type(error).__name__)

    async def twd_bars(self, code: str) -> tuple[list[PublicBar], bool]:
        """New Taiwan dollars for one unit of ``code``, each day, and whether closes only."""
        twd = await self.bars("usdtwd")
        if code == "USD":
            return twd, False
        pair, per_usd = PAIRS[code]
        return crossed(twd, await self.bars(pair), per_usd), True
