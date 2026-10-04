"""台指期 (TXF1)'s daily history, for its chart (D-180).

The futures exchange's open API (``market_strip.TAIFEX_FUTURES``) has only the latest day. Its
history is the 每日行情下載 page's CSV: every contract month of the TAIEX futures, the day
session (一般) and the night one (盤後), at most one month a request, Big5-encoded — and only to a
client that opened the page first (without that session the download answers "日期時間錯誤").

TXF1 is the near month, rolled at each expiry: a day's bar is that day's earliest monthly
contract (not a weekly one, ``202610W1``) in the day session. Kept as one more Taiwan symbol,
``TXF1``, beside the index (``price_history.INDEX``): five years on the first refresh, a month a
request with a pause between, and every later refresh only the months since its last stored day.
"""

from __future__ import annotations

import asyncio
import csv
import io
import logging
from collections.abc import Awaitable, Callable
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from autora.domains.newsroom.models import PriceBar
from autora.domains.newsroom.price_history import (
    FIRST_FILL_MONTHS,
    HISTORY_MONTHS,
    PAUSE_SECONDS,
    Bar,
    _months_back,
    _store,
    months_between,
)

log = logging.getLogger(__name__)

TXF1 = "TXF1"
TAIFEX_PAGE = "https://www.taifex.com.tw/cht/3/futDailyMarketView"
TAIFEX_DOWNLOAD = "https://www.taifex.com.tw/cht/3/futDataDown"
SOURCE = "TAIFEX"

GetCsv = Callable[[date, date], Awaitable[str]]
"""(first day, last day) within one month -> the download's text."""


def _price(text: str) -> Decimal | None:
    try:
        return Decimal(text.strip().replace(",", ""))
    except (InvalidOperation, AttributeError):
        return None  # "-": no trade


def parse_taifex_csv(text: str) -> list[Bar]:
    """Each day's near month in the day session, oldest first."""
    nearest: dict[date, tuple[str, Bar]] = {}
    for row in csv.reader(io.StringIO(text)):
        if len(row) < 18 or row[1].strip() != "TX" or row[17].strip() != "一般":
            continue
        month = row[2].strip()
        if not month.isdigit():
            continue  # a weekly contract
        try:
            day = date(*(int(part) for part in row[0].strip().split("/")))
        except (TypeError, ValueError):
            continue  # the header
        prices = [_price(cell) for cell in row[3:7]]
        if any(price is None for price in prices):
            continue
        volume = row[9].strip()
        bar = Bar(day, *prices, int(volume) if volume.isdigit() else 0)  # type: ignore[arg-type]
        if day not in nearest or month < nearest[day][0]:
            nearest[day] = (month, bar)
    return [nearest[day][1] for day in sorted(nearest)]


async def refresh_txf1(
    session: AsyncSession, get: GetCsv, *, today: date, pause: float = PAUSE_SECONDS
) -> int:
    """Bring TXF1's bars up to ``today``: the last year first, then back to five years.
    How many bars were written."""
    written, requests = 0, 0

    async def month_of(month: date) -> list[Bar] | None:
        nonlocal requests
        if requests:
            await asyncio.sleep(pause)
        requests += 1
        nxt = (month.replace(day=28) + timedelta(days=4)).replace(day=1)
        try:
            return parse_taifex_csv(await get(month, min(nxt - timedelta(days=1), today)))
        except Exception as error:  # noqa: BLE001 — one month missing is next time's
            log.warning("prices: TXF1 %s not read: %s", f"{month:%Y-%m}", type(error).__name__)
            return None

    first, last = (
        await session.execute(
            select(func.min(PriceBar.day), func.max(PriceBar.day)).where(
                PriceBar.market == "tw", PriceBar.symbol == TXF1
            )
        )
    ).one()
    start = last or _months_back(today, FIRST_FILL_MONTHS)
    for month in months_between(start, today):
        written += await _store(session, "tw", TXF1, await month_of(month) or [], source=SOURCE)
    await session.commit()  # the last year first: the chart is there before the rest
    # then the years before, from the earliest month there is or was just asked for
    earliest = min(first or start, start).replace(day=1)
    horizon = _months_back(today, HISTORY_MONTHS)
    if earliest > horizon:
        for month in reversed(months_between(horizon, earliest)[:-1]):
            written += await _store(session, "tw", TXF1, await month_of(month) or [], source=SOURCE)
        await session.commit()
    return written


def taifex_csv(timeout: float = 30.0) -> GetCsv:
    """The live download: the page first, for the session the download wants."""
    import httpx

    headers = {"User-Agent": "Mozilla/5.0 (compatible; AiSiWhale; +https://www.aisiwhale.com)"}

    async def get(first: date, last: date) -> str:
        async with httpx.AsyncClient(timeout=timeout, headers=headers) as client:
            (await client.get(TAIFEX_PAGE)).raise_for_status()
            response = await client.post(
                TAIFEX_DOWNLOAD,
                data={
                    "down_type": "1",
                    "commodity_id": "TX",
                    "commodity_id2": "",
                    "queryStartDate": f"{first:%Y/%m/%d}",
                    "queryEndDate": f"{last:%Y/%m/%d}",
                },
                headers={"Referer": TAIFEX_PAGE},
            )
            response.raise_for_status()
            text = response.content.decode("cp950", errors="replace")
            # the CSV comes as text/html too: told apart by what it says
            if "<html" in text[:600].lower():
                raise ValueError("TAIFEX answered a page, not the download")
            return text

    return get
