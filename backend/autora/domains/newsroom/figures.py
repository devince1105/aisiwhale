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

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from autora.domains.newsroom.forex import CHARTED, SOURCE, TiingoFx
from autora.domains.newsroom.price_history import INDEX, PublicBar, history

log = logging.getLogger(__name__)

FRED = "https://api.stlouisfed.org/fred/series/observations"
FRED_CHARTS = {"nasdaq": "NASDAQCOM", "us10y": "DGS10", "wti": "DCOILWTICO"}
"""The strip's FRED figures (``market_strip.FRED_SERIES``), by the strip's keys."""
COINS = {"btc": "btcusd", "eth": "ethusd"}
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
        if (code := currency_of(key)) is not None:
            bars, close_only = await self.forex.twd_bars(code)
            source = SOURCE
        elif key in FRED_CHARTS:
            bars = await self.fred.bars(FRED_CHARTS[key])
            source = "FRED"
        elif key in COINS:
            bars, close_only, source = await self.forex.crypto(COINS[key]), False, SOURCE
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
            bars=bars,
        )
