"""Spot gold's price and chart (D-070; on the watchlist, D-071): US dollars an ounce (XAU/USD),
each day's bar for about five years, and what that is in New Taiwan dollars a gram at the day's
dollar (``usdtwd``) — how a reader in Taiwan prices gold, and not Bank of Taiwan's gold passbook
price, which the page says. Both from the shared Tiingo forex cache (D-072).
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel

from autora.domains.newsroom.forex import SOURCE, TiingoFx
from autora.domains.newsroom.price_history import PublicBar

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
    """At the latest dollar in New Taiwan dollars; None without one."""
    source: str
    bars: list[PublicBar]
    """Oldest first, every day of about five years; gold has no volume, so ``v`` is 0."""


class GoldBoard:
    def __init__(self, forex: TiingoFx) -> None:
        self.forex = forex

    async def gold(self, lang: str) -> PublicGold | None:
        bars = await self.forex.bars("xauusd")
        if not bars:
            return None
        last = bars[-1]
        before = bars[-2].c if len(bars) > 1 else None
        dollar = await self.forex.bars("usdtwd")
        twd = dollar[-1].c if dollar else None
        return PublicGold(
            as_of=last.d,
            usd_per_oz=last.c,
            change=last.c - before if before else None,
            change_pct=(last.c - before) / before * 100 if before else None,
            twd_per_gram=last.c * twd / GRAMS_PER_OUNCE if twd else None,
            source=SOURCE,
            bars=bars,
        )
