"""新聞情緒 (D-091): how the week's news about each of the strip's stocks reads — positive,
neutral or negative toward the company — counted, with the headlines to check it by.

A description of coverage, not a forecast: no trend arrows, no "buy" or "sell"; the page says
so. The newsroom gives no advice (D-035).

- **Where the headlines come from.** A US stock: Finnhub's company news (the free plan; a
  week's headlines, many about other companies). A Taiwan stock: Yahoo 股市's feed for its code
  and 中央社's finance feed. Only a headline that names the stock is kept — its code or ticker as
  a whole word, or one of its names (``holdings._said``, as an article's stock links match).
- **How it is read.** New headlines only, a stock's in one model call (through the gateway, so
  the cost is the newsroom's and counted): each headline's tone toward the company as the
  headline itself puts it, with a short reason in each language. Not whether the price will
  move.
- **What is shown.** The last ``WINDOW`` days: how many headlines of each tone; how many there
  are against the four weeks before (熱度); the latest few, each with its tone and reason.
"""

from __future__ import annotations

import logging
import re
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Literal

from pydantic import BaseModel, Field, computed_field, field_validator
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from autora.domains.newsroom.feeds import FeedError, parse_feed
from autora.domains.newsroom.holdings import STOCKS, Stock, _said
from autora.domains.newsroom.models import Sentiment, StockHeadline

log = logging.getLogger(__name__)

SENTIMENT_SCHEDULE = "newsroom.stock_sentiment"
SENTIMENT_CRON = "0 0,9 * * *"
"""08:00 and 17:00 in Taipei: before Taiwan opens, and after it closes with the US's night news."""
WINDOW = timedelta(days=7)
HEAT_WEEKS = 4
MAX_NEW = 90
"""Headlines a stock sends to the model in one run, the newest first — a big US stock has a
hundred a week — in batches of ``BATCH``: a bound on what a run costs (cents)."""
BATCH = 30

FINNHUB_NEWS = "https://finnhub.io/api/v1/company-news"
YAHOO_TW = "https://tw.stock.yahoo.com/rss"
CNA_FINANCE = "https://feeds.feedburner.com/rsscna/finance"


@dataclass(frozen=True)
class Found:
    url: str
    title: str
    source: str
    published_at: datetime


GetJson = Callable[[str, dict], Awaitable[object]]
GetBytes = Callable[[str, dict], Awaitable[bytes]]


def _same(title: str) -> str:
    """A title as compared: without spaces or punctuation, so a copy's small changes still match."""
    return re.sub(r"[\W_]+", "", title).casefold()


def names_stock(stock: Stock, title: str) -> bool:
    return any(_said(term, title) for term in stock.terms)


def from_finnhub(stock: Stock, rows: object) -> list[Found]:
    out = []
    for row in rows if isinstance(rows, list) else []:
        title = str(row.get("headline") or "").strip()
        url = str(row.get("url") or "").strip()
        at = row.get("datetime")
        if title and url and isinstance(at, int | float) and names_stock(stock, title):
            source = str(row.get("source") or "Finnhub")
            out.append(Found(url, title, source, datetime.fromtimestamp(at, UTC)))
    return out


def from_feed(stock: Stock, body: bytes, source: str) -> list[Found]:
    try:
        entries = parse_feed(body)
    except FeedError:
        return []
    return [
        Found(entry.url, entry.title.strip(), source, entry.published_at)
        for entry in entries
        if entry.url and entry.published_at and names_stock(stock, entry.title)
    ]


# --- reading them -----------------------------------------------------------------------------


class Reading(BaseModel):
    index: int = Field(ge=1)
    sentiment: Literal["positive", "neutral", "negative"]
    """Anything else the model says ("mixed") is neutral, as the prompt defines it: one odd word
    failed a whole batch."""

    @field_validator("sentiment", mode="before")
    @classmethod
    def _as_one_of_three(cls, value: object) -> str:
        word = str(value).strip().lower()
        return word if word in ("positive", "neutral", "negative") else "neutral"

    reason_zh: str
    reason_en: str
    """Asked to be short; trimmed when stored, not refused (one long reason failed a whole
    stock's batch)."""


class Readings(BaseModel):
    readings: list[Reading]


PROMPT = """You read financial news headlines for a bilingual news site (Traditional Chinese and
English). For each numbered headline about the company named, say how the headline itself
reads toward that company: positive (good news for it: growth, orders, wins, upgrades),
negative (bad news for it: losses, cuts, probes, downgrades) or neutral (neither, mixed, or not
really about it). Judge the headline as written; do not predict the share price and do not
give advice. Give each a short reason: reason_zh in Traditional Chinese (never Simplified, at
most 40 characters), reason_en in English (at most 20 words).

Reply with only JSON: {"readings": [{"index": 1, "sentiment": "positive|neutral|negative",
"reason_zh": "...", "reason_en": "..."}, ...]} — one reading for every headline."""

Classify = Callable[[str, list[str]], Awaitable[list[Reading]]]
"""(the company's name, its headlines) -> one reading a headline, in order."""


def gateway_classifier(gateway, company_id: uuid.UUID, project_id: uuid.UUID | None) -> Classify:
    """Headlines read by the model the analysts use, through the gateway: every call recorded
    and charged to the newsroom's budget."""
    from autora.runtime.models.types import CallContext, Message, ModelRequest

    async def classify(company: str, titles: list[str]) -> list[Reading]:
        numbered = "\n".join(f"{i}. {title}" for i, title in enumerate(titles, 1))
        response = await gateway.complete(
            ModelRequest(
                capability="research_extraction",
                context=CallContext(
                    company_id=company_id,
                    project_id=project_id,
                    role="analyst",
                    task_name="stock_sentiment",
                ),
                system=PROMPT,
                messages=[Message.user(f"Company: {company}\n\n{numbered}")],
                output_model=Readings,
                max_output_tokens=4096,
            )
        )
        if not isinstance(response.parsed, Readings):
            raise ValueError("the model's readings did not parse")
        return response.parsed.readings

    return classify


# --- a run --------------------------------------------------------------------------------------


async def gather(
    stock: Stock, finnhub: GetJson | None, feed: GetBytes, cna: bytes | None, today: date
) -> list[Found]:
    """The stock's headlines of the last ``WINDOW``, from its market's sources."""
    since = today - WINDOW
    if stock.market == "us":
        if finnhub is None:
            return []
        rows = await finnhub(
            FINNHUB_NEWS,
            {"symbol": stock.symbol, "from": since.isoformat(), "to": today.isoformat()},
        )
        return from_finnhub(stock, rows)
    found = from_feed(stock, await feed(YAHOO_TW, {"s": stock.symbol}), "Yahoo股市")
    if cna:
        found += from_feed(stock, cna, "中央社")
    return found


async def refresh(
    session: AsyncSession,
    *,
    classify: Classify,
    finnhub: GetJson | None,
    feed: GetBytes,
    now: datetime | None = None,
    stocks: tuple[Stock, ...] | None = None,
) -> int:
    """Gather each stock's new headlines and read them. How many were read."""
    now = now or datetime.now(UTC)
    today = now.date()
    try:
        cna = await feed(CNA_FINANCE, {})
    except Exception as error:  # noqa: BLE001 — Yahoo's still stand
        log.warning("sentiment: 中央社 not read: %s", type(error).__name__)
        cna = None
    read = 0
    for stock in stocks or tuple(STOCKS.values()):
        try:
            found = await gather(stock, finnhub, feed, cna, today)
        except Exception as error:  # noqa: BLE001 — one stock's source is next time's
            log.warning("sentiment: %s not gathered: %s", stock.key, type(error).__name__)
            continue
        # one story, one headline: Yahoo often carries 中央社's own — the same title at another
        # address — and counted twice it would tilt the week
        known = {
            _same(title)
            for title in await session.scalars(
                select(StockHeadline.title).where(
                    StockHeadline.stock_key == stock.key,
                    StockHeadline.published_at >= now - WINDOW * (HEAT_WEEKS + 1),
                )
            )
        }
        by_url: dict[str, Found] = {}
        for f in found:
            if _same(f.title) not in known:
                known.add(_same(f.title))
                by_url.setdefault(f.url, f)
        if by_url:
            await session.execute(
                insert(StockHeadline)
                .values(
                    [
                        {
                            "id": uuid.uuid4(),
                            "stock_key": stock.key,
                            "url": f.url,
                            "title": f.title[:500],
                            "source": f.source,
                            "published_at": f.published_at,
                        }
                        for f in by_url.values()
                    ]  # fmt: skip
                )
                .on_conflict_do_nothing(index_elements=["stock_key", "url"])
            )
            await session.commit()
        unread = (
            await session.scalars(
                select(StockHeadline)
                .where(
                    StockHeadline.stock_key == stock.key,
                    StockHeadline.sentiment.is_(None),
                    StockHeadline.published_at >= now - WINDOW,
                )
                .order_by(StockHeadline.published_at.desc())
                .limit(MAX_NEW)
            )
        ).all()
        if not unread:
            continue
        company = f"{stock.zh}（{stock.en}, {stock.symbol}）"
        for start in range(0, len(unread), BATCH):
            batch = unread[start : start + BATCH]
            try:
                readings = await classify(company, [h.title for h in batch])
            except Exception as error:  # noqa: BLE001 — read next time
                log.warning("sentiment: %s not read: %s", stock.key, type(error).__name__)
                await session.rollback()
                break
            for reading in readings:
                if 1 <= reading.index <= len(batch):
                    headline = batch[reading.index - 1]
                    headline.sentiment = Sentiment(reading.sentiment).value
                    headline.reason_zh = reading.reason_zh[:60]
                    headline.reason_en = reading.reason_en[:160]
                    headline.classified_at = now
                    read += 1
            await session.commit()
    return read


# --- what a page shows --------------------------------------------------------------------------


class PublicHeadline(BaseModel):
    title: str
    url: str
    source: str
    published_at: datetime
    sentiment: Literal["positive", "neutral", "negative"]
    reason: str | None


class PublicSentiment(BaseModel):
    key: str
    name: str
    positive: int
    neutral: int
    negative: int
    heat: float | None
    """This week's headlines against the four weeks before's weekly average (1.0: as usual);
    None before there are four weeks to compare with."""
    headlines: list[PublicHeadline]
    """The latest read, newest first."""

    @computed_field
    @property
    def total(self) -> int:
        return self.positive + self.neutral + self.negative


async def stock_sentiment(
    session: AsyncSession,
    stock: Stock,
    lang: str,
    *,
    now: datetime | None = None,
    headlines: int = 6,
) -> PublicSentiment:
    now = now or datetime.now(UTC)
    since = now - WINDOW
    counts = dict(
        (
            await session.execute(
                select(StockHeadline.sentiment, func.count())
                .where(
                    StockHeadline.stock_key == stock.key,
                    StockHeadline.sentiment.is_not(None),
                    StockHeadline.published_at >= since,
                )
                .group_by(StockHeadline.sentiment)
            )
        ).all()
    )
    before = await session.scalar(
        select(func.count()).where(
            StockHeadline.stock_key == stock.key,
            StockHeadline.sentiment.is_not(None),
            StockHeadline.published_at >= since - WINDOW * HEAT_WEEKS,
            StockHeadline.published_at < since,
        )
    )
    first = await session.scalar(
        select(func.min(StockHeadline.published_at)).where(StockHeadline.stock_key == stock.key)
    )
    week = sum(counts.values())
    enough = first is not None and first <= since - WINDOW * HEAT_WEEKS
    heat = round(week / (before / HEAT_WEEKS), 2) if enough and before else None
    rows = (
        await session.scalars(
            select(StockHeadline)
            .where(
                StockHeadline.stock_key == stock.key,
                StockHeadline.sentiment.is_not(None),
                StockHeadline.published_at >= since,
            )
            .order_by(StockHeadline.published_at.desc())
            .limit(headlines)
        )
    ).all()
    zh = lang.startswith("zh")
    return PublicSentiment(
        key=stock.key,
        name=stock.zh if zh else stock.en,
        positive=counts.get(Sentiment.POSITIVE.value, 0),
        neutral=counts.get(Sentiment.NEUTRAL.value, 0),
        negative=counts.get(Sentiment.NEGATIVE.value, 0),
        heat=heat,
        headlines=[
            PublicHeadline(
                title=h.title,
                url=h.url,
                source=h.source,
                published_at=h.published_at,
                sentiment=h.sentiment,
                reason=h.reason_zh if zh else h.reason_en,
            )  # fmt: skip
            for h in rows
        ],
    )


# --- the schedule --------------------------------------------------------------------------------


def feed_reader(timeout: float = 20.0) -> GetBytes:
    import httpx

    async def get(url: str, params: dict) -> bytes:
        headers = {"User-Agent": "Mozilla/5.0 (AiSiWhale news sentiment)"}
        async with httpx.AsyncClient(
            timeout=timeout, follow_redirects=True, headers=headers
        ) as client:
            response = await client.get(url, params=params)
            if response.is_error:
                raise RuntimeError(f"HTTP {response.status_code} from {response.url.host}")
            return response.content

    return get


async def no_feed(url: str, params: dict) -> bytes:
    """Offline (fixtures, tests): no feed, and nothing is asked of anybody."""
    return b""


class SentimentKeeper:
    """The ``newsroom.stock_sentiment`` handler: for the investing newsroom only (its no-advice
    policy on), whose budget the model's reading is charged to; the headlines are everybody's."""

    def __init__(self, gateway, finnhub: GetJson | None, feed: GetBytes) -> None:
        self.gateway = gateway
        self.finnhub = finnhub
        self.feed = feed

    def schedule_handler(self):
        async def handler(session: AsyncSession, schedule, scheduled_for: datetime) -> None:
            from autora.db.models import Project
            from autora.db.repositories.companies import get_policies
            from autora.domains.newsroom.advice import no_advice

            if self.gateway is None or not no_advice(
                await get_policies(session, schedule.company_id)
            ):
                return
            project = await session.scalar(
                select(Project.id).where(Project.company_id == schedule.company_id).limit(1)
            )
            classify = gateway_classifier(self.gateway, schedule.company_id, project)
            await refresh(session, classify=classify, finnhub=self.finnhub, feed=self.feed)

        return handler
