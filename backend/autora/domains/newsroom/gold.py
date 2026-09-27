"""The 黃金 tab's reference price and chart (D-070): spot gold in US dollars an ounce (XAU/USD),
each day's bar for about five years, from Tiingo's forex prices — the key the stock charts use
(D-059), one request a few times a day. Beside it, what that is in New Taiwan dollars a gram at
the day's reference rate (D-069): how a reader in Taiwan prices gold, and not Bank of Taiwan's
gold passbook price, which the page says.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta

from pydantic import BaseModel

from autora.domains.newsroom.fx_rates import FxBoard
from autora.domains.newsroom.price_history import GetRows, PublicBar

log = logging.getLogger(__name__)

TIINGO_GOLD = "https://api.tiingo.com/tiingo/fx/xauusd/prices"
SOURCE = "Tiingo"
YEARS = 5
KEEP = timedelta(hours=3)
"""How long one answer serves every reader: the day's bar moves until the day is done."""
RETRY = timedelta(minutes=30)
GRAMS_PER_OUNCE = 31.1034768
"""A troy ounce, which gold is priced in."""


class PublicGold(BaseModel):
    as_of: date
    """The latest bar's day."""
    usd_per_oz: float
    change: float | None
    change_pct: float | None
    """Against the day before's close."""
    twd_per_gram: float | None
    """At the day's reference rate (D-069); None without one."""
    source: str
    bars: list[PublicBar]
    """Oldest first, every day of about five years; gold has no volume, so ``v`` is 0."""


def bars_from(rows: list[dict]) -> list[PublicBar]:
    """Tiingo's daily forex rows as one bar a trading day, oldest first (the last row said for a
    day wins). Gold trades again from Sunday evening (UTC) — Monday morning in Taipei — and
    Tiingo gives that a Sunday bar: it is folded into the Monday after. A weekend bar with no
    trading yet (open, high, low and close all the same) is left out."""
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
            monday = day + timedelta(days=7 - day.weekday())
            bar = bar.model_copy(update={"d": monday})
            day = monday
        if (kept := out.get(day)) is not None:
            # the Sunday evening that opened this Monday: its open, the day's range, the close
            later = bar if bar is not kept else kept
            bar = PublicBar(
                d=day,
                o=kept.o,
                h=max(kept.h, later.h),
                l=min(kept.l, later.l),
                c=later.c,
                v=0,
            )
        out[day] = bar
    return [out[d] for d in sorted(out)]


class GoldBoard:
    """One per process: Tiingo is asked once per ``KEEP`` for every reader. ``get`` is None
    offline (fixtures, tests) or without Tiingo's key: no gold board."""

    def __init__(
        self,
        get: GetRows | None,
        fx: FxBoard,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.get = get
        self.fx = fx
        self.clock = clock
        self._bars: list[PublicBar] = []
        self._until = datetime.min.replace(tzinfo=UTC)
        self._lock = asyncio.Lock()

    async def gold(self, lang: str) -> PublicGold | None:
        if self.get is None:
            return None
        async with self._lock:
            now = self.clock()
            if now >= self._until:
                try:
                    start = now.date() - timedelta(days=366 * YEARS)
                    rows = await self.get(
                        TIINGO_GOLD, {"startDate": start.isoformat(), "resampleFreq": "1day"}
                    )
                    bars = bars_from(rows)
                    if not bars:
                        raise ValueError("no bars")
                    self._bars = bars
                    self._until = now + KEEP
                except Exception as error:  # noqa: BLE001 — the last good answer stands
                    log.warning("gold: not refreshed: %s", type(error).__name__)
                    self._until = now + RETRY
        if not self._bars:
            return None
        last = self._bars[-1]
        before = self._bars[-2].c if len(self._bars) > 1 else None
        board = await self.fx.board(lang)
        usd = next((r.twd for r in board.rates if r.code == "USD"), None) if board else None
        return PublicGold(
            as_of=last.d,
            usd_per_oz=last.c,
            change=last.c - before if before else None,
            change_pct=(last.c - before) / before * 100 if before else None,
            twd_per_gram=last.c * usd / GRAMS_PER_OUNCE if usd else None,
            source=SOURCE,
            bars=self._bars,
        )
