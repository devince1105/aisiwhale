"""財經行事曆 (D-088): what is coming in the next few weeks, for the site's sidebar.

- US economic releases, from FRED's release dates (the St. Louis Fed publishes each release's
  schedule): CPI, the jobs report, GDP, personal income and outlays (PCE), retail sales. The key
  the market strip already uses.
- Earnings dates of the strip's US stocks (TSMC's through its ADR), from Finnhub's earnings
  calendar — on its free plan, one symbol a request — with before or after the US market.

The Fed's rate decisions are not here: FRED's "FOMC Press Release" lists every day, not the
meeting days, and a list of dates typed in by hand could not be checked.

Asked for twice a day (``KEEP``) for every reader; the last good answer stands when a service
does not give one. Offline (fixtures, tests), there is no calendar.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime, timedelta
from typing import Literal

from pydantic import BaseModel

log = logging.getLogger(__name__)

FRED_DATES = "https://api.stlouisfed.org/fred/release/dates"
FINNHUB_EARNINGS = "https://finnhub.io/api/v1/calendar/earnings"
AHEAD = timedelta(days=45)
KEEP = timedelta(hours=12)
RETRY = timedelta(hours=1)

RELEASES: dict[int, tuple[str, str]] = {
    10: ("美國消費者物價指數（CPI）", "US CPI"),
    50: ("美國就業報告（非農就業）", "US jobs report"),
    53: ("美國 GDP", "US GDP"),
    54: ("美國個人所得與支出（PCE）", "US personal income and PCE"),
    9: ("美國零售銷售", "US retail sales"),
}
"""FRED release ids (checked 2026-09-28) and how the calendar names each."""

EARNINGS = ("NVDA", "AAPL", "GOOGL", "MSFT", "AMZN", "TSM", "META", "AVGO", "TSLA", "MU", "AMD")
"""The strip's US stocks that report earnings (its ETFs, QQQ and VOO, do not)."""
HOURS = {"bmo": ("盤前", "before the open"), "amc": ("盤後", "after the close")}

GetJson = Callable[[str, dict], Awaitable[dict]]


class PublicEvent(BaseModel):
    day: date
    kind: Literal["macro", "earnings"]
    key: str
    """A release (``cpi``…) or a stock as the strip keys it (``us:NVDA``): its chart's link."""
    name: str
    detail: str | None = None
    """An earnings date's timing (盤後) and fiscal quarter."""


def _names(stock_names: dict[str, tuple[str, str]], symbol: str) -> tuple[str, str]:
    zh, en = stock_names.get(symbol, (symbol, symbol))
    if symbol == "TSM":  # TSMC reports once: under its own name, not its ADR's
        zh, en = "台積電", "TSMC"
    return zh, en


class EconomicCalendar:
    """One per process. ``fred``/``finnhub`` are the services' JSON readers, None without a key
    (or offline): that half of the calendar is left out."""

    def __init__(
        self,
        fred: GetJson | None,
        finnhub: GetJson | None,
        stock_names: dict[str, tuple[str, str]],
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.fred = fred
        self.finnhub = finnhub
        self.stock_names = stock_names
        self.clock = clock
        self._rows: list[tuple[date, str, str, int | str, str | None, str | None]] = []
        self._until = datetime.min.replace(tzinfo=UTC)
        self._lock = asyncio.Lock()

    async def _fetch(self, today: date) -> list[tuple]:
        rows: list[tuple] = []
        end = today + AHEAD
        if self.fred is not None:
            for release in RELEASES:
                answer = await self.fred(
                    FRED_DATES,
                    {
                        "release_id": release,
                        "realtime_start": today.isoformat(),
                        "realtime_end": end.isoformat(),
                        "include_release_dates_with_no_data": "true",
                        "sort_order": "asc",
                    },
                )
                for row in answer.get("release_dates") or []:
                    rows.append(
                        (date.fromisoformat(row["date"]), "macro", "release", release, None, None)
                    )
        if self.finnhub is not None:
            for symbol in EARNINGS:
                answer = await self.finnhub(
                    FINNHUB_EARNINGS,
                    {"from": today.isoformat(), "to": end.isoformat(), "symbol": symbol},
                )
                for row in answer.get("earningsCalendar") or []:
                    quarter = f"{row['year']}Q{row['quarter']}" if row.get("quarter") else None
                    rows.append(
                        (date.fromisoformat(row["date"]), "earnings", "stock", symbol,
                         row.get("hour") or None, quarter)
                    )  # fmt: skip
        return rows

    async def events(self, lang: str, *, limit: int = 8) -> list[PublicEvent]:
        if self.fred is None and self.finnhub is None:
            return []
        now = self.clock()
        today = (now + timedelta(hours=8)).date()  # Taipei's day, as the site's
        async with self._lock:
            if now >= self._until:
                try:
                    self._rows = await self._fetch(today)
                    self._until = now + KEEP
                except Exception as error:  # noqa: BLE001 — the last good answer stands
                    log.warning("economic calendar: not refreshed: %s", type(error).__name__)
                    self._until = now + RETRY
        zh = lang.startswith("zh")
        out = []
        rows = sorted(self._rows, key=lambda r: (r[0], r[1] != "macro"))  # a day's data first
        for day, kind, _, what, hour, quarter in rows:
            if day < today:
                continue
            if kind == "macro":
                names = RELEASES[int(what)]
                out.append(PublicEvent(day=day, kind="macro", key=f"release:{what}",
                                       name=names[0] if zh else names[1]))  # fmt: skip
            else:
                name_zh, name_en = _names(self.stock_names, str(what))
                timing = HOURS.get(hour or "")
                detail = " ".join(
                    part for part in (quarter, timing[0 if zh else 1] if timing else None) if part
                )
                out.append(
                    PublicEvent(
                        day=day,
                        kind="earnings",
                        key=f"us:{what}",
                        name=f"{name_zh} 財報" if zh else f"{name_en} earnings",
                        detail=detail or None,
                    )  # fmt: skip
                )
        return out[:limit]


def _reader(
    key_param: str, api_key: str, extra: dict | None = None, timeout: float = 20.0
) -> GetJson:
    """A JSON reader whose key travels in the query string: an error never carries the URL."""
    import httpx

    async def get(url: str, params: dict) -> dict:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url, params={**params, **(extra or {}), key_param: api_key})
            if response.is_error:
                raise RuntimeError(f"HTTP {response.status_code} from {response.url.host}")
            return response.json()

    return get


def fred_json(api_key: str) -> GetJson:
    return _reader("api_key", api_key, {"file_type": "json"})


def finnhub_json(api_key: str) -> GetJson:
    return _reader("token", api_key)
