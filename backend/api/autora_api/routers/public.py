"""The public site's API (T-515, D-025): published articles and the reader beacon.

Most articles are free and need no sign-in. A members-only one comes back as its opening and
``locked`` unless the reader's cookie belongs to somebody whose membership is still running —
the rest of the text is never sent to a browser that may not read it. The beacon carries
nothing about the reader either way.

- GET  /api/public/articles?lang=zh-TW[&company=<slug>][&section=ai…][&limit=20][&offset=0]:
  newest published first (``section`` may be given more than once: any of them)
- GET  /api/public/articles/{lang}/{slug}: one published article (404: not published in lang)
- GET  /api/public/markets: the market strip's figures, closing or delayed (D-048)
- GET  /api/public/stocks/{symbol}?lang=zh-TW[&company=<slug>]: a stock's page — its figure, the
  tracked investors' 13F positions in it, our articles that name it (D-049)
- GET  /api/public/stocks/{symbol}/history: its daily bars for the chart (D-059)
- GET  /api/public/stocks/{symbol}/intraday: a US stock's last five days in 15-minute bars
- POST /api/analytics/beacon: {article_id, lang, event_type, session_hash} -> 204
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from functools import lru_cache
from typing import Annotated, Literal

from fastapi import APIRouter, Cookie, Depends, HTTPException, Path, Query, Response, status
from pydantic import BaseModel, Field, SecretStr
from sqlalchemy import select

from autora.accounts import SESSION_COOKIE, customer_ref, reader_for
from autora.company import memberships
from autora.db.models import Company
from autora.domains.newsroom import forex as currencies
from autora.domains.newsroom import securities
from autora.domains.newsroom.figures import (
    Figures,
    FredHistory,
    PublicFigure,
    fred_observations,
)
from autora.domains.newsroom.forex import TiingoFx
from autora.domains.newsroom.gold import GoldBoard, PublicGold
from autora.domains.newsroom.holdings import STOCKS, PublicHolder, holders
from autora.domains.newsroom.market_strip import (
    PublicQuote,
    QuoteBoard,
    build_board,
    forex_quote,
)
from autora.domains.newsroom.models import AnalyticsEventType
from autora.domains.newsroom.official_trades import PublicTrade, trades_for
from autora.domains.newsroom.price_history import (
    IntradayCache,
    PublicHistory,
    PublicIntraday,
    bar_quote,
    history,
    refresh_us,
    tiingo_rows,
)
from autora.domains.newsroom.site import (
    MAX_LIST,
    BeaconRejected,
    PublicArticle,
    PublicArticleSummary,
    count_articles_mentioning,
    count_published_articles,
    published_article,
    published_articles,
    published_articles_mentioning,
    record_beacon,
)
from autora.infra.settings import get_settings
from autora_api.deps import Session

router = APIRouter(tags=["public"])

Section = Literal[
    "holdings", "figures", "ai", "tw", "us", "crypto", "institutions", "gold", "commodities", "fx"
]
"""The site's sections (``newsroom.sources.SECTIONS``), spelled out for the OpenAPI document."""

SessionCookie = Annotated[str | None, Cookie(alias=SESSION_COOKIE)]

Lang = Annotated[str, Field(pattern=r"^[a-z]{2}(-[A-Z][A-Za-z]{1,3})?$", max_length=10)]


@router.get("/api/public/articles")
async def list_articles(
    session: Session,
    response: Response,
    lang: Annotated[str, Query(pattern=r"^[a-z]{2}(-[A-Z][A-Za-z]{1,3})?$", max_length=10)],
    company: Annotated[str | None, Query(max_length=100)] = None,
    section: Annotated[list[Section] | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_LIST)] = 20,
    offset: Annotated[int, Query(ge=0, le=10_000)] = 0,
) -> list[PublicArticleSummary]:
    """Newest first; ``offset`` pages through them (D-047). ``X-Total-Count`` says how many
    there are in all, for the list's page numbers (D-065)."""
    total = await count_published_articles(session, lang, company_slug=company, section=section)
    response.headers["X-Total-Count"] = str(total)
    return await published_articles(
        session, lang, company_slug=company, section=section, limit=limit, offset=offset
    )


@router.get("/api/public/articles/{lang}/{slug}")
async def get_article(
    lang: str, slug: str, session: Session, autora_reader: SessionCookie = None
) -> PublicArticle:
    article = await published_article(session, lang, slug)
    if article is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no published article {slug} in {lang}")
    if not article.locked:
        return article
    reader = await reader_for(session, autora_reader)
    if reader is None:
        return article
    until = await memberships.access_until(
        session, company_id=article.company_id, customer_ref=customer_ref(reader.id)
    )
    if until is None:
        return article
    return await published_article(session, lang, slug, unlocked=True) or article


@lru_cache
def market_board() -> QuoteBoard:
    """One board per process: it is the cache, so every reader is served from the same one."""
    settings = get_settings()
    return build_board(
        fred_api_key=_secret(settings.fred_api_key),
        finnhub_api_key=_secret(settings.finnhub_api_key),
        forex=forex_cache(),
    )


def _secret(value: SecretStr | None) -> str | None:
    return value.get_secret_value() if value else None


@lru_cache
def forex_cache() -> TiingoFx:
    """One per process (D-072): gold and currencies from Tiingo, each pair asked for once every
    few hours for the strip, the watchlist's charts and gold's price a gram."""
    settings = get_settings()
    key = _secret(settings.tiingo_api_key)
    live = settings.tools_profile == "live" and key is not None
    return TiingoFx(tiingo_rows(key) if live else None)


def gold_board(forex: Annotated[TiingoFx, Depends(forex_cache)]) -> GoldBoard:
    return GoldBoard(forex)


@router.get("/api/public/gold")
async def gold(
    response: Response,
    board: Annotated[GoldBoard, Depends(gold_board)],
    lang: Annotated[str, Query(pattern=r"^[a-z]{2}(-[A-Z][A-Za-z]{1,3})?$", max_length=10)],
) -> PublicGold | None:
    """Spot gold's price and chart (D-070, on the watchlist since D-071): US dollars an ounce,
    each day for about five years, and what that is in New Taiwan dollars a gram. None when
    there is none to show."""
    response.headers["Cache-Control"] = "public, max-age=600"
    return await board.gold(lang)


@lru_cache
def fred_history() -> FredHistory:
    """One per process (D-072): each FRED series' five years, asked for every six hours."""
    settings = get_settings()
    key = _secret(settings.fred_api_key)
    live = settings.tools_profile == "live" and key is not None
    return FredHistory(fred_observations(key) if live else None)


def figure_charts(
    forex: Annotated[TiingoFx, Depends(forex_cache)],
    fred: Annotated[FredHistory, Depends(fred_history)],
) -> Figures:
    return Figures(forex, fred)


@router.get("/api/public/figures/{key}")
async def figure_chart(
    key: Annotated[str, Path(pattern=r"^[a-z0-9]{2,10}$")],
    session: Session,
    response: Response,
    figures: Annotated[Figures, Depends(figure_charts)],
) -> PublicFigure | None:
    """A watchlist figure's chart (D-072, D-073): a currency against the New Taiwan dollar
    (``jpytwd``), the Nasdaq, the 10-year yield, WTI crude, the Taiwan index, Bitcoin or Ether —
    each day for about five years. None for a figure without one (or offline)."""
    response.headers["Cache-Control"] = "public, max-age=600"
    return await figures.figure(key, session)


@router.get("/api/public/markets")
async def markets(board: Annotated[QuoteBoard, Depends(market_board)]) -> list[PublicQuote]:
    """The figures under the site's header, in the order shown; one a service never gave is
    left out rather than shown as zero."""
    return await board.quotes()


class PublicStock(BaseModel):
    symbol: str
    market: str
    """``us`` or ``tw``."""
    name: str
    """In the language asked for."""
    quote: PublicQuote | None
    """From the market strip's board; None when its service has not answered."""
    holders: list[PublicHolder]
    """The tracked investors' positions in it (a Taiwan stock: in its US listing), largest first."""
    trades: list[PublicTrade] = []
    """Public officials' trades in it, from their checked transaction reports (D-051)."""
    articles: list[PublicArticleSummary]
    articles_total: int = 0
    """How many of our stories name it in all: ``articles`` is ten of them (D-066)."""
    us_listing: str | None = None
    """Where it trades in the US: its own symbol, or a Taiwan stock's ADR (TSM for 2330). None:
    US filings (13F holders, officials' trades) can say nothing about it."""
    exchange: str | None = None
    """TPEx for an over-the-counter Taiwan stock (its code reads .TWO); None for the strip's."""
    tracks_13f: bool = False
    """Whether its 13F holders are looked for: the strip's stocks, whose CUSIPs are known. Any
    other stock (D-061) has no 13F section, rather than one saying nobody holds it."""


@lru_cache
def intraday_cache() -> IntradayCache:
    """One per process, like the board: the ten-minute cache every reader shares."""
    key = _secret(get_settings().tiingo_api_key)
    return IntradayCache(tiingo_rows(key) if key else None)


@router.get("/api/public/stocks/{symbol}/intraday")
async def get_stock_intraday(
    symbol: str,
    session: Session,
    response: Response,
    cache: Annotated[IntradayCache, Depends(intraday_cache)],
) -> PublicIntraday:
    """A US stock's last five trading days in 15-minute bars (D-059), from Tiingo's IEX feed.
    Empty for a Taiwan stock (no free intraday history) or without Tiingo's key."""
    stock = await securities.find(session, symbol)
    if stock is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no page for {symbol}")
    response.headers["Cache-Control"] = "public, max-age=300"
    if stock.market != "us":
        return PublicIntraday(symbol=stock.symbol, source=None, bars=[])
    return await cache.bars(stock.symbol)


async def _first_us_bars(session, stock) -> bool:
    """A US stock nobody asked about before: its five years from Tiingo, now (one request). The
    page asks for its figure and its chart at once, so either may be first."""
    key = _secret(get_settings().tiingo_api_key)
    if stock.market != "us" or not key:
        return False
    written = await refresh_us(
        session, tiingo_rows(key), today=datetime.now(UTC).date(), symbols=(stock.symbol,),
        pause=0,
    )  # fmt: skip
    return written > 0


@router.get("/api/public/stocks/{symbol}/history")
async def get_stock_history(symbol: str, session: Session, response: Response) -> PublicHistory:
    """A stock's daily bars for its chart (D-059): oldest first, about five years.

    Any listed stock (D-061): asking tracks it, so its prices are kept from then on. A US stock
    with none yet is fetched there and then (one Tiingo request); a Taiwan one is filled by the
    worker within minutes (the exchanges answer a month at a time), and says ``preparing``."""
    stock = await securities.find(session, symbol)
    if stock is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no page for {symbol}")
    await securities.track(session, stock)
    answer = await history(session, stock.market, stock.symbol)
    if not answer.bars and await _first_us_bars(session, stock):
        answer = await history(session, stock.market, stock.symbol)
    await session.commit()
    if not answer.bars and stock.market == "tw":
        answer.preparing = True
        response.headers["Cache-Control"] = "no-store"
    else:
        response.headers["Cache-Control"] = "public, max-age=600"  # new bars twice a day
    return answer


@router.get("/api/public/stocks/{symbol}")
async def get_stock(
    symbol: str,
    session: Session,
    board: Annotated[QuoteBoard, Depends(market_board)],
    lang: Annotated[str, Query(pattern=r"^[a-z]{2}(-[A-Z][A-Za-z]{1,3})?$", max_length=10)],
    company: Annotated[str | None, Query(max_length=100)] = None,
    articles_offset: Annotated[int, Query(ge=0, le=10_000)] = 0,
) -> PublicStock:
    """``articles_offset`` pages through our stories that name it, ten at a time (D-066)."""
    stock = await securities.find(session, symbol)
    if stock is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no page for {symbol}")
    company_id = None
    if company is not None:
        company_id = await session.scalar(select(Company.id).where(Company.slug == company))
        if company_id is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"no company {company}")
    # the strip's twenty from its board; any other from its last stored close (D-061)
    quote = next((q for q in await board.quotes() if q.key == stock.key), None)
    if quote is None and stock.symbol not in STOCKS:
        await securities.track(session, stock)
        quote = await bar_quote(session, stock.market, stock.symbol)
        if quote is None and await _first_us_bars(session, stock):
            quote = await bar_quote(session, stock.market, stock.symbol)
        await session.commit()
    return PublicStock(
        symbol=stock.symbol,
        market=stock.market,
        name=stock.zh if lang.startswith("zh") else stock.en,
        quote=quote,
        holders=await holders(session, stock, company_id=company_id),
        trades=await trades_for(session, stock.tickers, company_id=company_id),
        articles=await published_articles_mentioning(
            session, lang, _terms(stock), company_slug=company, offset=articles_offset
        ),
        articles_total=await count_articles_mentioning(
            session, lang, _terms(stock), company_slug=company
        ),
        us_listing=stock.tickers[0] if stock.tickers else None,
        tracks_13f=bool(stock.cusips),
        exchange=stock.exchange,
    )


def _terms(stock) -> tuple[str, ...]:
    """What an article naming it would say. A ticker of one or two letters ("A", "GE") is left
    out for a stock off the strip: as a whole word it is in too many sentences."""
    if stock.symbol in STOCKS:
        return stock.terms
    return tuple(t for t in stock.terms if not (t.isascii() and len(t) < 3))


class PublicSecurity(BaseModel):
    symbol: str
    market: str
    name: str
    name_en: str | None
    exchange: str
    kind: str


def _currencies(query: str) -> list[PublicSecurity]:
    """Currencies with a chart against the New Taiwan dollar whose code or name has ``query``
    in it (D-072): 歐元, EUR or euro find ``EURTWD``."""
    q = query.strip().lower()
    return [
        PublicSecurity(
            symbol=f"{code}TWD", market="market", name=zh, name_en=en, exchange="Tiingo", kind="fx"
        )
        for code, zh, en in currencies.CURRENCIES
        if code in currencies.CHARTED and (q in code.lower() or q in zh or q in en.lower())
    ]


@router.get("/api/public/securities")
async def search_securities(
    session: Session,
    response: Response,
    q: Annotated[str, Query(min_length=1, max_length=40)],
    limit: Annotated[int, Query(ge=1, le=20)] = 12,
) -> list[PublicSecurity]:
    """Any listed Taiwan or US stock (D-061), by code, ticker or name; and a currency against the
    New Taiwan dollar (D-072), by its name or code — ``EURTWD``, market ``market``, kind ``fx``."""
    response.headers["Cache-Control"] = "public, max-age=3600"
    return _currencies(q) + [
        PublicSecurity(
            symbol=row.symbol,
            market=row.market,
            name=row.name,
            name_en=row.name_en,
            exchange=row.exchange,
            kind=row.kind,
        )  # fmt: skip
        for row in await securities.search(session, q, limit=limit)
    ]


@router.get("/api/public/quotes")
async def get_quotes(
    session: Session,
    board: Annotated[QuoteBoard, Depends(market_board)],
    keys: Annotated[str, Query(max_length=2000, description="tw:2330,us:PLTR — at most 60")],
    forex: Annotated[TiingoFx, Depends(forex_cache)],
) -> list[PublicQuote]:
    """Quotes for a watchlist (D-061): the strip's own for its stocks, the last stored close for
    any other. A key without a quote yet is left out."""
    wanted = list(dict.fromkeys(k.strip() for k in keys.split(",") if k.strip()))[:60]
    strip = {q.key: q for q in await board.quotes()}
    out = []
    for key in wanted:
        if key in strip:
            out.append(strip[key])
            continue
        # a currency the reader added (D-072): its last close from the shared cache
        if (q := await forex_quote(forex, key)) is not None:
            out.append(q)
            continue
        market, _, symbol = key.partition(":")
        if market in ("tw", "us") and symbol and (q := await bar_quote(session, market, symbol)):
            out.append(q)
    return out


class Beacon(BaseModel):
    article_id: uuid.UUID
    lang: Lang
    event_type: AnalyticsEventType
    session_hash: str = Field(
        pattern=r"^[0-9a-f]{16,64}$",
        description="A random id the reader's browser makes each day; nothing about the reader.",
    )


@router.post("/api/analytics/beacon", status_code=status.HTTP_204_NO_CONTENT)
async def beacon(body: Beacon, session: Session) -> Response:
    """Count a view or a completed read. A repeat from the same session that day is dropped
    (still 204: the reader's page has nothing to do about it)."""
    try:
        await record_beacon(
            session,
            article_id=body.article_id,
            lang=body.lang,
            event_type=body.event_type,
            session_hash=body.session_hash,
        )
    except BeaconRejected as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from None
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
