"""A chart for a watchlist figure that is not a stock (D-072): what it has been each day for about
five years, for the watchlist page to show when the figure is picked.

- A currency against the New Taiwan dollar (``usdtwd``, ``jpytwd``, any ``<code>twd`` with a
  pair, ``forex.CHARTED``): the shared Tiingo cache.
- The Nasdaq Composite, the US 10-year yield and WTI crude: FRED — the series the strip already
  reads (``market_strip.FRED_SERIES``), the whole of them from five years back, one request a
  series every six hours. FRED's key travels in the query string, so a failure is logged by its
  kind only.

- The Taiwan index (``taiex``, D-073): its days as TWSE's index history gives them, stored with the
  Taiwan stocks' (``price_history.INDEX``) — five years is sixty requests, too many to ask again.
- Bitcoin and Ether (``btc``, ``eth``, D-073): Tiingo's crypto prices, through the same cache.

FRED's figures and a currency cross are each day's close and nothing more (``close_only``): the
chart draws the close and gives no open, high or low. Spot gold has a page of its own (``gold``):
its price a gram.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime, timedelta
from typing import Literal

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from autora.domains.newsroom.forex import CHARTED, SOURCE, TiingoFx
from autora.domains.newsroom.price_history import INDEX, PublicBar, history

log = logging.getLogger(__name__)

FRED = "https://api.stlouisfed.org/fred/series/observations"
FRED_CHARTS = {"nasdaq": "NASDAQCOM", "us10y": "DGS10", "wti": "DCOILWTICO"}
"""The strip's FRED figures (``market_strip.FRED_SERIES``), by the strip's keys."""
COINS = {"btc": "btcusd", "eth": "ethusd"}
GRAINS = {
    "maize": ("PMAIZMTUSDM", "玉米（IMF 月價）", "Corn (IMF monthly)", "CORN"),
    "soybeans": ("PSOYBUSDM", "黃豆（IMF 月價）", "Soybeans (IMF monthly)", "SOYB"),
    "wheat": ("PWHEAMTUSDM", "小麥（IMF 月價）", "Wheat (IMF monthly)", "WEAT"),
}
"""Corn, soybeans and wheat (D-080): the IMF's world price, US dollars a metric ton, a month at a
time and about two months behind (FRED) — and each grain's Teucrium fund, a US ETF that holds
CBOT futures, for the days between. No free source gives CBOT's own daily futures prices. Keyed
``maize``: CORN is the fund's ticker."""
YEARS = 5
KEEP = timedelta(hours=6)
"""FRED publishes each of these once a day."""
RETRY = timedelta(minutes=30)

GetObservations = Callable[[str], Awaitable[list[dict]]]
"""series id -> its observations since five years back, oldest first."""


def currency_of(key: str) -> str | None:
    """``jpytwd`` is the yen against the New Taiwan dollar: its code, if it has a chart."""
    key = key.lower()
    code = key[:3].upper()
    return code if len(key) == 6 and key.endswith("twd") and code in CHARTED else None


def closes(observations: list[dict]) -> list[PublicBar]:
    """FRED's observations as each day's close; "." is a day without one (a holiday)."""
    out = []
    for row in observations:
        try:
            value = float(row["value"])
            day = date.fromisoformat(row["date"])
        except (KeyError, TypeError, ValueError):
            continue
        out.append(PublicBar(d=day, o=value, h=value, l=value, c=value, v=0))
    return out


class PublicFigure(BaseModel):
    key: str
    as_of: date
    value: float
    change: float | None
    change_pct: float | None
    """None for the yield: its change is in percentage points (``change``)."""
    source: str
    close_only: bool
    """Each day's close and no more (FRED, a currency cross): open, high and low are the close."""
    interval: Literal["day", "month"] = "day"
    """A bar a day, or a month (the IMF's grain prices, D-080): then a chart of months only."""
    bars: list[PublicBar]
    """Oldest first, about five years."""


class FredHistory:
    """Each series' five years, kept ``KEEP``; the last good answer stands. ``get`` is None
    offline or without FRED's key."""

    def __init__(
        self,
        get: GetObservations | None,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.get = get
        self.clock = clock
        self._kept: dict[str, list[PublicBar]] = {}
        self._until: dict[str, datetime] = {}
        self._lock = asyncio.Lock()

    async def bars(self, series: str) -> list[PublicBar]:
        if self.get is None:
            return []
        async with self._lock:
            now = self.clock()
            if now >= self._until.get(series, datetime.min.replace(tzinfo=UTC)):
                try:
                    fresh = closes(await self.get(series))
                    if not fresh:
                        raise ValueError("no observations")
                    self._kept[series] = fresh
                    self._until[series] = now + KEEP
                except Exception as error:  # noqa: BLE001 — never the URL: the key is in it
                    log.warning("fred: %s not refreshed: %s", series, type(error).__name__)
                    self._until[series] = now + RETRY
        return self._kept.get(series, [])


def fred_observations(api_key: str, timeout: float = 20.0) -> GetObservations:
    import httpx

    async def get(series: str) -> list[dict]:
        start = datetime.now(UTC).date() - timedelta(days=366 * YEARS)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(
                FRED,
                params={
                    "series_id": series,
                    "api_key": api_key,
                    "file_type": "json",
                    "observation_start": start.isoformat(),
                },
            )
            return response.raise_for_status().json()["observations"]

    return get


class Figures:
    def __init__(self, forex: TiingoFx, fred: FredHistory) -> None:
        self.forex = forex
        self.fred = fred

    async def figure(self, key: str, session: AsyncSession | None = None) -> PublicFigure | None:
        key = key.lower()
        close_only = True
        interval: Literal["day", "month"] = "day"
        if (code := currency_of(key)) is not None:
            bars, close_only = await self.forex.twd_bars(code)
            source = SOURCE
        elif key in FRED_CHARTS:
            bars = await self.fred.bars(FRED_CHARTS[key])
            source = "FRED"
        elif key in COINS:
            bars, close_only, source = await self.forex.crypto(COINS[key]), False, SOURCE
        elif key in GRAINS:
            bars, source, interval = await self.fred.bars(GRAINS[key][0]), "IMF (FRED)", "month"
        elif key == "taiex" and session is not None:
            stored = await history(session, "tw", INDEX)
            bars, close_only, source = stored.bars, False, "TWSE"
        else:
            return None
        if not bars:
            return None
        last = bars[-1]
        before = bars[-2].c if len(bars) > 1 else None
        change = last.c - before if before else None
        return PublicFigure(
            key=key,
            as_of=last.d,
            value=last.c,
            change=change,
            change_pct=None if change is None or key == "us10y" else change / before * 100,
            source=source,
            close_only=close_only,
            interval=interval,
            bars=bars,
        )


# --- the figures an article names (D-079) --------------------------------------------------------

FIGURE_TERMS: dict[str, tuple[str, str, tuple[str, ...]]] = {
    "xau": ("黃金", "Gold", ("黃金", "金價", "XAU", "gold", "Gold")),
    "wti": ("西德州原油", "WTI crude", ("原油", "油價", "WTI", "crude", "Crude")),
    "btc": ("比特幣", "Bitcoin", ("比特幣", "Bitcoin", "BTC")),
    "eth": ("以太幣", "Ether", ("以太幣", "以太坊", "Ether", "Ethereum", "ETH")),
    "taiex": ("加權指數", "TAIEX", ("加權指數", "台股大盤", "發行量加權", "TAIEX")),
    # the grains (D-080): the IMF's monthly price, and the Teucrium fund that holds the futures
    **{
        key: (zh, en, terms)
        for key, (_, zh, en, _), terms in (
            (k, GRAINS[k], t)
            for k, t in (
                ("maize", ("玉米", "corn", "Corn")),
                ("soybeans", ("黃豆", "大豆", "soybean", "Soybean", "soybeans", "Soybeans")),
                ("wheat", ("小麥", "wheat", "Wheat")),
            )
        )
    },
    "us:CORN": ("玉米 ETF", "Corn ETF", ("玉米", "corn", "Corn")),
    "us:SOYB": ("黃豆 ETF", "Soybean ETF", ("黃豆", "大豆", "soybean", "Soybean", "soybeans")),
    "us:WEAT": ("小麥 ETF", "Wheat ETF", ("小麥", "wheat", "Wheat")),
    "nasdaq": ("那斯達克", "Nasdaq", ("那斯達克", "那指", "Nasdaq")),
    # not 殖利率 alone: in Taiwan that is most often a stock's dividend yield
    "us10y": (
        "美國10年期公債",
        "US 10Y",
        ("公債殖利率", "美債殖利率", "10年期", "Treasury yield", "Treasury yields", "10-year"),
    ),
}
"""A watchlist figure, its names (zh, en) and what an article that names it would say."""
CURRENCY_ALIASES = {
    "USD": ("美元", "美金", "US dollar", "U.S. dollar"),
    "JPY": ("日圓", "日元", "日幣", "yen"),
    "CNY": ("人民幣", "yuan", "renminbi"),
    "EUR": ("歐元", "euro", "Euro"),
    "HKD": ("港幣", "港元", "Hong Kong dollar"),
    "KRW": ("韓元", "韓圜"),  # not "won": it is also what a currency did
}
"""Beyond Bank of Taiwan's name: how a story says the currency."""
SECTION_FIGURES = {
    "tw": ("taiex",),
    "us": ("nasdaq", "us10y"),
    "crypto": ("btc", "eth"),
    "gold": ("xau",),
    "commodities": (
        "wti",
        "xau",
        "maize",
        "us:CORN",
        "soybeans",
        "us:SOYB",
        "wheat",
        "us:WEAT",
    ),  # fmt: skip
}
"""Which figures a section's stories may link (D-079); 外匯 links its currencies."""


def figures_named(text: str, section: str | None) -> list[tuple[str, str, str]]:
    """The watchlist figures a story in ``section`` names (D-079), as (key, zh, en): a coin in
    crypto news, gold in gold news, oil and gold among futures, the currencies in FX news."""
    from autora.domains.newsroom.forex import NAMES
    from autora.domains.newsroom.holdings import _said

    out = []
    for key in SECTION_FIGURES.get(section or "", ()):
        zh, en, terms = FIGURE_TERMS[key]
        if any(_said(term, text) for term in terms):
            out.append((key, zh, en))
    if section == "fx":
        for code in CHARTED:
            zh, en = NAMES[code]
            terms = (zh, *CURRENCY_ALIASES.get(code, ()))
            if any(_said(term, text) for term in terms):
                out.append((f"{code.lower()}twd", zh, en))
    return out[:8]
