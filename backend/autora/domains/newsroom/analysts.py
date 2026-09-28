"""分析師評等 (D-096): how many analysts rate a US stock strong buy, buy, hold, sell or strong
sell this month — Finnhub's recommendation trends, as reported, with the month before to compare.

What others say, counted and credited: the site draws no verdict from it (D-035) — no needle, no
"買入". Finnhub's free plan has it for US stocks only (checked 2026-09-28: ``2330.TW`` and price
targets are paid); TSMC reads through its ADR, and says so. Asked for at most twice a day per
stock, for every reader; the last good answer stands when Finnhub does not give one.
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta

from pydantic import BaseModel, computed_field

from autora.domains.newsroom.economic_calendar import GetJson

log = logging.getLogger(__name__)

FINNHUB_RECOMMENDATION = "https://finnhub.io/api/v1/stock/recommendation"
KEEP = timedelta(hours=12)
RETRY = timedelta(hours=1)
ADRS = {"2330": "TSM"}
"""A Taiwan stock whose US listing analysts rate."""
US_SYMBOL = re.compile(r"^[A-Z][A-Z.\-]{0,9}$")


class Counts(BaseModel):
    period: date
    """The month Finnhub counts (its first day)."""
    strong_buy: int
    buy: int
    hold: int
    sell: int
    strong_sell: int

    @computed_field
    @property
    def total(self) -> int:
        return self.strong_buy + self.buy + self.hold + self.sell + self.strong_sell


class PublicRatings(BaseModel):
    symbol: str
    via: str | None = None
    """The listing rated in its place: ``TSM`` for 2330."""
    latest: Counts
    previous: Counts | None = None
    source: str = "Finnhub"


def _counts(row: dict) -> Counts:
    return Counts(
        period=date.fromisoformat(row["period"]),
        strong_buy=int(row.get("strongBuy") or 0),
        buy=int(row.get("buy") or 0),
        hold=int(row.get("hold") or 0),
        sell=int(row.get("sell") or 0),
        strong_sell=int(row.get("strongSell") or 0),
    )


class AnalystRatings:
    """One per process. ``finnhub`` is its JSON reader, None without a key (or offline)."""

    def __init__(
        self, finnhub: GetJson | None, *, clock: Callable[[], datetime] = lambda: datetime.now(UTC)
    ) -> None:
        self.finnhub = finnhub
        self.clock = clock
        self._kept: dict[str, tuple[datetime, PublicRatings | None]] = {}
        self._lock = asyncio.Lock()

    async def ratings(self, symbol: str) -> PublicRatings | None:
        symbol = symbol.upper()
        via = ADRS.get(symbol)
        asked = via or symbol
        if self.finnhub is None or not US_SYMBOL.match(asked):
            return None
        now = self.clock()
        async with self._lock:
            kept = self._kept.get(asked)
            if kept and now < kept[0]:
                found = kept[1]
            else:
                try:
                    rows = await self.finnhub(FINNHUB_RECOMMENDATION, {"symbol": asked})
                    rows = sorted(
                        (r for r in rows or [] if isinstance(r, dict) and r.get("period")),
                        key=lambda r: r["period"],
                        reverse=True,
                    )
                    found = (
                        PublicRatings(
                            symbol=asked,
                            latest=_counts(rows[0]),
                            previous=_counts(rows[1]) if len(rows) > 1 else None,
                        )
                        if rows
                        else None
                    )
                    self._kept[asked] = (now + KEEP, found)
                except Exception as error:  # noqa: BLE001 — the last good answer stands
                    log.warning("analyst ratings: %s not read: %s", asked, type(error).__name__)
                    found = kept[1] if kept else None
                    self._kept[asked] = (now + RETRY, found)
        if found is None or not found.latest.total:
            return None
        return found.model_copy(update={"symbol": symbol, "via": via})
