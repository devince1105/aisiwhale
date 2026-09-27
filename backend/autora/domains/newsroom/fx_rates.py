"""The 外匯 tab's reference rates (D-069): what one unit of each foreign currency Bank of Taiwan
posts is worth in New Taiwan dollars.

Bank of Taiwan's own posted rates (rate.bot.com.tw) sit behind a bot check and are in no open
dataset, so they are not fetched: the page links to them for the rates a bank actually buys and
sells at. The figures here are ExchangeRate-API's open access rates (open.er-api.com, no key): a
market mid rate, updated once a day. Its terms ask for a link on the page that shows them
("Rates By Exchange Rate API"), allow caching and do not allow passing the data on — so the site
shows them, and asks for them once per update: the answer says when the next one is.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

from pydantic import BaseModel

log = logging.getLogger(__name__)

ENDPOINT = "https://open.er-api.com/v6/latest/TWD"
SOURCE = "ExchangeRate-API"
SOURCE_URL = "https://www.exchangerate-api.com"
BANK_URL = "https://rate.bot.com.tw/xrt?Lang=zh-TW"

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

RETRY = timedelta(hours=1)
"""After a failed ask, how long the last good answer (or none) stands before asking again."""


class PublicFxRate(BaseModel):
    code: str
    name: str
    """In the language asked for, as Bank of Taiwan names it."""
    twd: float
    """New Taiwan dollars for one unit."""


class PublicFxBoard(BaseModel):
    as_of: datetime
    """When the provider last updated these."""
    source: str
    source_url: str
    bank_url: str
    """Bank of Taiwan's posted rates: what a bank buys and sells at."""
    rates: list[PublicFxRate]


GetJson = Callable[[str], Awaitable[dict]]


def board_from(answer: dict, lang: str) -> PublicFxBoard | None:
    """The provider's answer (per one New Taiwan dollar) as the board shows it (per one unit of
    each currency); None for an answer that is not a success."""
    if answer.get("result") != "success" or answer.get("base_code") != "TWD":
        return None
    per_twd = answer.get("rates") or {}
    zh = lang.startswith("zh")
    rates = [
        PublicFxRate(code=code, name=name_zh if zh else name_en, twd=1 / per_twd[code])
        for code, name_zh, name_en in CURRENCIES
        if isinstance(per_twd.get(code), int | float) and per_twd[code] > 0
    ]
    if not rates:
        return None
    return PublicFxBoard(
        as_of=datetime.fromtimestamp(int(answer["time_last_update_unix"]), UTC),
        source=SOURCE,
        source_url=SOURCE_URL,
        bank_url=BANK_URL,
        rates=rates,
    )


class FxBoard:
    """One per process: the provider is asked once per update, and every reader is served the
    same answer. ``get`` is None offline (fixtures, tests): no board, and nobody is asked."""

    def __init__(
        self,
        get: GetJson | None,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.get = get
        self.clock = clock
        self._answer: dict | None = None
        self._until = datetime.min.replace(tzinfo=UTC)
        self._lock = asyncio.Lock()

    async def board(self, lang: str) -> PublicFxBoard | None:
        if self.get is None:
            return None
        async with self._lock:
            now = self.clock()
            if now >= self._until:
                try:
                    answer = await self.get(ENDPOINT)
                    if answer.get("result") != "success":
                        raise ValueError(answer.get("error-type") or "not a success")
                    self._answer = answer
                    # the answer says when the provider updates next; a few minutes after it
                    next_at = int(answer.get("time_next_update_unix") or 0)
                    self._until = max(
                        datetime.fromtimestamp(next_at, UTC) + timedelta(minutes=5), now + RETRY
                    )
                except Exception as error:  # noqa: BLE001 — the last good answer stands
                    log.warning("fx rates: not refreshed: %s", type(error).__name__)
                    self._until = now + RETRY
        return board_from(self._answer, lang) if self._answer else None


def http_json(timeout: float = 15.0) -> GetJson:
    import httpx

    async def get(url: str) -> dict:
        async with httpx.AsyncClient(timeout=timeout) as client:
            return (await client.get(url)).raise_for_status().json()

    return get
