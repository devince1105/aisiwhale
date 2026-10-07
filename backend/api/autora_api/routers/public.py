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
- GET  /api/public/holdings?lang=zh-TW[&company=<slug>]: the holdings dashboard's cards (HD-05)
- GET  /api/public/holdings/people/{slug}?lang=zh-TW[&company=<slug>]: a person page — the whole
  table only for a reader signed in (D-159), the first ten for anybody
- GET  /api/public/institutions?lang=zh-TW[&period=][&q=][&sort=value|change|filed][&order=]
  [&limit=50][&offset=0]: 機構排行, every 13F filer's quarter in dollars (HD-11)
- GET  /api/public/institutions/{cik}?lang=zh-TW[&period=]: an institution's page — its largest
  ten holdings for anybody, the rest and its buys and sells signed in; queued if never asked
- GET  /api/public/tw-flows[?day=][&group=foreign|trust|dealer|total][&side=buy|sell]: a trading
  day's largest net buying or selling by Taiwan's three institutional investors (HD-12)
- POST /api/analytics/beacon: {article_id, lang, event_type, session_hash} -> 204
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from functools import lru_cache
from typing import Annotated, Literal

from fastapi import APIRouter, Cookie, Depends, HTTPException, Path, Query, Response, status
from pydantic import BaseModel, Field, SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from autora.accounts import SESSION_COOKIE, reader_for
from autora.accounts.entitlement import Capability, entitlement_for
from autora.company.office_theme import DEFAULT_OFFICE_THEME, OfficeTheme, office_theme
from autora.db.models import Company
from autora.db.session import get_sessionmaker
from autora.domains.newsroom import forex as currencies
from autora.domains.newsroom import securities
from autora.domains.newsroom.analysts import AnalystRatings, PublicRatings
from autora.domains.newsroom.economic_calendar import (
    EconomicCalendar,
    PublicEvent,
    finnhub_json,
    fred_json,
)
from autora.domains.newsroom.figures import (
    GRAINS,
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
from autora.domains.newsroom.portfolios import (
    PublicPortfolio,
    PublicPortfolioCard,
    cards,
    portfolio,
)
from autora.domains.newsroom.price_history import (
    IntradayCache,
    PublicHistory,
    PublicIntraday,
    TwIntradayCache,
    bar_quote,
    fugle_json,
    history,
    refresh_us,
    tiingo_rows,
)
from autora.domains.newsroom.rankings import (
    PublicInstitution,
    PublicRanking,
    institution,
    ranking,
)
from autora.domains.newsroom.sentiment import PublicSentiment, stock_sentiment
from autora.domains.newsroom.site import (
    MAX_LIST,
    BeaconRejected,
    PublicArticle,
    PublicArticleSummary,
    PublicDay,
    count_articles_mentioning,
    count_published_articles,
    popular_articles,
    published_article,
    published_articles,
    published_articles_mentioning,
    published_days,
    record_beacon,
)
from autora.domains.newsroom.tw_flows import PublicFlowRanking, PublicTwFlows, for_stock
from autora.domains.newsroom.tw_flows import ranking as flow_ranking
from autora.infra.blobstore import BlobNotFound, InvalidBlobKey, build_blob_store
from autora.infra.settings import get_settings
from autora_api.deps import Session

router = APIRouter(tags=["public"])

Section = Literal[
    "holdings", "figures", "ai", "tw", "us", "crypto", "institutions", "gold", "commodities", "fx"
]
"""The site's sections (``newsroom.sources.SECTIONS``), spelled out for the OpenAPI document."""

SessionCookie = Annotated[str | None, Cookie(alias=SESSION_COOKIE)]

Lang = Annotated[str, Field(pattern=r"^[a-z]{2}(-[A-Z][A-Za-z]{1,3})?$", max_length=10)]


@router.get("/api/public/covers/{story_id}/{name}", include_in_schema=False)
async def get_cover(story_id: uuid.UUID, name: str) -> Response:
    """A cover kept in the blob store (D-142: dev, without R2). With R2 the site loads covers
    from the bucket's public address and this is never asked."""
    if not name.endswith(".webp"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such cover")
    blobs = build_blob_store(get_settings())
    try:
        data = await blobs.get(f"covers/{story_id}/{name}")
    except (BlobNotFound, InvalidBlobKey):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such cover") from None
    return Response(
        data, media_type="image/webp", headers={"Cache-Control": "public, max-age=86400"}
    )


@router.get("/api/public/articles")
async def list_articles(
    session: Session,
    response: Response,
    lang: Annotated[str, Query(pattern=r"^[a-z]{2}(-[A-Z][A-Za-z]{1,3})?$", max_length=10)],
    company: Annotated[str | None, Query(max_length=100)] = None,
    section: Annotated[list[Section] | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_LIST)] = 20,
    offset: Annotated[int, Query(ge=0, le=10_000)] = 0,
    day: Annotated[date | None, Query(description="Only that day's, in Taipei (D-084)")] = None,
) -> list[PublicArticleSummary]:
    """Newest first; ``offset`` pages through them (D-047). ``X-Total-Count`` says how many
    there are in all, for the list's page numbers (D-065)."""
    total = await count_published_articles(
        session, lang, company_slug=company, section=section, day=day
    )
    response.headers["X-Total-Count"] = str(total)
    return await published_articles(
        session, lang, company_slug=company, section=section, limit=limit, offset=offset, day=day
    )


@lru_cache
def economic_calendar() -> EconomicCalendar:
    """One per process (D-088): FRED's release dates and Finnhub's earnings, twice a day."""
    settings = get_settings()
    live = settings.tools_profile == "live"
    fred = _secret(settings.fred_api_key)
    finnhub = _secret(settings.finnhub_api_key)
    return EconomicCalendar(
        fred_json(fred) if live and fred else None,
        finnhub_json(finnhub) if live and finnhub else None,
        {symbol: (stock.zh, stock.en) for symbol, stock in STOCKS.items()},
    )


@lru_cache
def analyst_ratings() -> AnalystRatings:
    """One per process (D-096): Finnhub's analyst counts, each stock at most twice a day."""
    settings = get_settings()
    finnhub = _secret(settings.finnhub_api_key)
    live = settings.tools_profile == "live"
    return AnalystRatings(finnhub_json(finnhub) if live and finnhub else None)


@router.get("/api/public/stocks/{symbol}/analysts")
async def get_analyst_ratings(
    symbol: Annotated[str, Path(max_length=12)],
    response: Response,
    ratings: Annotated[AnalystRatings, Depends(analyst_ratings)],
) -> PublicRatings | None:
    """分析師評等 (D-096): how many analysts rate a US stock each way this month and last, as
    Finnhub reports it — no verdict of the site's. TSMC through its ADR; None for the rest of
    Taiwan's and when there is none."""
    response.headers["Cache-Control"] = "public, max-age=3600"
    return await ratings.ratings(symbol)


@router.get("/api/public/events")
async def events(
    response: Response,
    calendar: Annotated[EconomicCalendar, Depends(economic_calendar)],
    lang: Annotated[str, Query(pattern=r"^[a-z]{2}(-[A-Z][A-Za-z]{1,3})?$", max_length=10)],
    limit: Annotated[int, Query(ge=1, le=20)] = 8,
) -> list[PublicEvent]:
    """財經行事曆 (D-088): the coming weeks' US economic releases and the strip's earnings dates,
    soonest first."""
    response.headers["Cache-Control"] = "public, max-age=1800"
    return await calendar.events(lang, limit=limit)


@router.get("/api/public/articles/popular")
async def popular(
    session: Session,
    response: Response,
    lang: Annotated[str, Query(pattern=r"^[a-z]{2}(-[A-Z][A-Za-z]{1,3})?$", max_length=10)],
    company: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=10)] = 5,
) -> list[PublicArticleSummary]:
    """熱門文章 (D-086): the most read over the last week, the front page's sidebar."""
    response.headers["Cache-Control"] = "public, max-age=300"
    return await popular_articles(session, lang, company_slug=company, limit=limit)


@router.get("/api/public/articles/calendar")
async def article_calendar(
    session: Session,
    response: Response,
    lang: Annotated[str, Query(pattern=r"^[a-z]{2}(-[A-Z][A-Za-z]{1,3})?$", max_length=10)],
    month: Annotated[str, Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$", description="2026-09")],
    company: Annotated[str | None, Query(max_length=100)] = None,
    section: Annotated[list[Section] | None, Query()] = None,
) -> list[PublicDay]:
    """The days of a month (Taipei's) with published articles, and how many each (D-084): the
    calendar a reader pages back through the stories with."""
    response.headers["Cache-Control"] = "public, max-age=300"
    year, number = (int(part) for part in month.split("-"))
    return await published_days(
        session, lang, date(year, number, 1), company_slug=company, section=section
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
    granted = await entitlement_for(session, reader, company_id=article.company_id)
    if granted.can(Capability.READ_VIP_ARTICLES):
        return await published_article(session, lang, slug, reader="member") or article
    if article.lock == "sign_in" and granted.can(Capability.READ_SIGN_IN_SECTIONS):
        # 持股觀察: signed in is enough (D-159)
        return await published_article(session, lang, slug, reader="signed_in") or article
    return article


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
    few hours for the strip, the watchlist's charts and gold's price a gram — kept in the
    database, so a restart does not ask again (D-082)."""
    settings = get_settings()
    key = _secret(settings.tiingo_api_key)
    if settings.tools_profile != "live" or key is None:
        return TiingoFx(None)
    return TiingoFx(tiingo_rows(key), sessions=get_sessionmaker())


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


class PublicOfficeTheme(BaseModel):
    theme: OfficeTheme


@router.get("/api/public/office-theme")
async def public_office_theme(
    session: Session, company: Annotated[str | None, Query(max_length=100)] = None
) -> PublicOfficeTheme:
    """The style the site's AI 編輯部 is shown in: its company's, chosen in the back office
    (D-178). An unknown company, or none named, has the default."""
    found = (
        await session.scalar(select(Company).where(Company.slug == company)) if company else None
    )
    if found is None:
        return PublicOfficeTheme(theme=DEFAULT_OFFICE_THEME)
    return PublicOfficeTheme(theme=await office_theme(session, found.id))


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
    institutional: PublicTwFlows | None = None
    """A Taiwan stock's 三大法人 and foreign ownership, day by day (HD-12); None for a US one,
    or before the exchanges' figures for it are read."""


@lru_cache
def intraday_cache() -> IntradayCache:
    """One per process, like the board: the ten-minute cache every reader shares."""
    key = _secret(get_settings().tiingo_api_key)
    return IntradayCache(tiingo_rows(key) if key else None)


@lru_cache
def tw_intraday_cache() -> TwIntradayCache:
    """One per process, like the US one (D-074): Fugle asked once per stock every ten minutes."""
    key = _secret(get_settings().fugle_api_key)
    return TwIntradayCache(fugle_json(key) if key else None)


@router.get("/api/public/stocks/{symbol}/intraday")
async def get_stock_intraday(
    symbol: str,
    session: Session,
    response: Response,
    cache: Annotated[IntradayCache, Depends(intraday_cache)],
    tw_cache: Annotated[TwIntradayCache, Depends(tw_intraday_cache)],
) -> PublicIntraday:
    """A stock's last five trading days in 15-minute bars: a US stock's from Tiingo's IEX feed
    (D-059), a Taiwan stock's from Fugle (D-074). Empty without that service's key."""
    stock = await securities.find(session, symbol)
    if stock is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no page for {symbol}")
    response.headers["Cache-Control"] = "public, max-age=300"
    if stock.market == "tw":
        return await tw_cache.bars(stock.symbol)
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


@router.get("/api/public/stocks/{symbol}/sentiment")
async def get_stock_sentiment(
    symbol: str,
    session: Session,
    response: Response,
    lang: Annotated[str, Query(pattern=r"^[a-z]{2}(-[A-Z][A-Za-z]{1,3})?$", max_length=10)],
) -> PublicSentiment | None:
    """新聞情緒 (D-091): how the week's headlines about one of the strip's stocks read toward it,
    counted, with the latest few and why. None for a stock off the strip (its news is not read)."""
    response.headers["Cache-Control"] = "public, max-age=600"
    stock = STOCKS.get(symbol.upper())
    return await stock_sentiment(session, stock, lang) if stock else None


@router.get("/api/public/sentiment")
async def sentiment_overview(
    session: Session,
    response: Response,
    lang: Annotated[str, Query(pattern=r"^[a-z]{2}(-[A-Z][A-Za-z]{1,3})?$", max_length=10)],
) -> list[PublicSentiment]:
    """新聞情緒 for every stock on the strip with a week's headlines, the most covered first (for
    the sidebar); each without its headlines."""
    response.headers["Cache-Control"] = "public, max-age=600"
    out = [await stock_sentiment(session, stock, lang, headlines=0) for stock in STOCKS.values()]
    return sorted((s for s in out if s.total), key=lambda s: -s.total)


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
        holders=await holders(session, stock, company_id=company_id, lang=lang),
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
        institutional=await for_stock(session, stock.symbol) if stock.market == "tw" else None,
    )


async def _company_id(session: AsyncSession, company: str | None) -> uuid.UUID | None:
    """The company a public page asks about by its slug; None: not narrowed (404: no such)."""
    if company is None:
        return None
    company_id = await session.scalar(select(Company.id).where(Company.slug == company))
    if company_id is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no company {company}")
    return company_id


@router.get("/api/public/holdings")
async def get_holdings(
    session: Session,
    response: Response,
    lang: Annotated[str, Query(pattern=r"^[a-z]{2}(-[A-Z][A-Za-z]{1,3})?$", max_length=10)],
    company: Annotated[str | None, Query(max_length=100)] = None,
) -> list[PublicPortfolioCard]:
    """The holdings dashboard's cards (HD-05): each followed 13F filer's largest holdings, its
    latest moves and its simulated one-year return. Nothing in them depends on the reader."""
    company_id = await _company_id(session, company)
    response.headers["Cache-Control"] = "public, max-age=600"  # a run every twenty minutes
    return await cards(session, company_id, lang)


@router.get("/api/public/holdings/people/{slug}")
async def get_portfolio(
    slug: Annotated[str, Path(max_length=50)],
    session: Session,
    response: Response,
    lang: Annotated[str, Query(pattern=r"^[a-z]{2}(-[A-Z][A-Za-z]{1,3})?$", max_length=10)],
    company: Annotated[str | None, Query(max_length=100)] = None,
    autora_reader: SessionCookie = None,
) -> PublicPortfolio:
    """A person page (HD-05). Open to anybody; the whole table only for a reader signed in —
    free (D-159) — so the answer differs by reader and is not to be kept by anybody between."""
    company_id = await _company_id(session, company)
    reader = await reader_for(session, autora_reader)
    page = await portfolio(session, company_id, slug, lang, signed_in=reader is not None)
    if page is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no holdings page for {slug}")
    response.headers["Cache-Control"] = "private, no-store"
    return page


LANG = Query(pattern=r"^[a-z]{2}(-[A-Z][A-Za-z]{1,3})?$", max_length=10)


@router.get("/api/public/institutions")
async def get_ranking(
    session: Session,
    response: Response,
    lang: Annotated[str, LANG],
    period: date | None = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    sort: Literal["value", "change", "filed"] = "value",
    order: Literal["desc", "asc"] = "desc",
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0, le=20_000)] = 0,
) -> PublicRanking:
    """機構排行 (HD-11): every 13F filer's quarter, largest first, in dollars. The same for
    every reader; a quarter not offered is the default one (the latest all due)."""
    response.headers["Cache-Control"] = "public, max-age=600"  # the index is read every ten
    return await ranking(
        session,
        lang=lang,
        period=period,
        q=q,
        sort=sort,
        ascending=order == "asc",
        limit=limit,
        offset=offset,
    )


@router.get("/api/public/institutions/{cik}")
async def get_institution(
    cik: Annotated[str, Path(pattern=r"^\d{1,10}$")],
    session: Session,
    response: Response,
    lang: Annotated[str, LANG],
    period: date | None = None,
    autora_reader: SessionCookie = None,
) -> PublicInstitution:
    """An institution's page (HD-11): open to anybody, its ten largest holdings; the rest, and
    its estimated buys and sells, for a reader signed in (free, D-159). Opened for the first
    time, its holdings are queued to be worked out (404: no 13F for the quarter)."""
    reader = await reader_for(session, autora_reader)
    page = await institution(session, cik, lang=lang, period=period, signed_in=reader is not None)
    if page is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no 13F from {cik} for the quarter")
    await session.commit()  # a page queued is kept
    response.headers["Cache-Control"] = "private, no-store"
    return page


@router.get("/api/public/tw-flows")
async def get_tw_flows(
    session: Session,
    response: Response,
    day: date | None = None,
    group: Literal["foreign", "trust", "dealer", "total"] = "foreign",
    side: Literal["buy", "sell"] = "buy",
) -> PublicFlowRanking:
    """A trading day's largest net buying (or selling) by foreign investors, investment trusts,
    dealers or the three together (HD-12): TWSE's and TPEx's own figures, the same for every
    reader. A day not offered is the latest one."""
    response.headers["Cache-Control"] = "public, max-age=600"
    return await flow_ranking(session, day=day, group=group, side=side)


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


STRIP_FIGURES: tuple[tuple[str, str, str, str, str, tuple[str, ...]], ...] = (
    ("TAIEX", "加權指數", "TAIEX", "TWSE", "index", ("台股", "大盤", "加權")),
    ("TXF1", "台指期", "TAIEX futures", "TAIFEX", "future", ("台指", "期貨", "TX", "TXF")),
    ("NASDAQ", "那斯達克", "Nasdaq", "FRED", "index", ("那指",)),
    ("US10Y", "美國10年期公債", "US 10Y", "FRED", "rate", ("公債", "殖利率", "treasury")),
    ("WTI", "西德州原油", "WTI crude", "FRED", "spot", ("原油", "油價", "oil")),
    ("XAU", "黃金", "Gold", "Tiingo", "spot", ("金價",)),
    ("BTC", "比特幣", "Bitcoin", "CoinGecko", "crypto", ()),
    ("ETH", "以太幣", "Ether", "CoinGecko", "crypto", ("以太坊", "ethereum")),
)
"""The strip's figures a reader may keep (D-062), found by search too (D-189): by symbol, by name
or by what people call it — 台指 or TX for 台指期. (symbol, zh, en, source, kind, also called)"""


def _figures(query: str) -> list[PublicSecurity]:
    q = query.strip().lower()
    return [
        PublicSecurity(
            symbol=symbol, market="market", name=zh, name_en=en, exchange=source, kind=kind
        )
        for symbol, zh, en, source, kind, also in STRIP_FIGURES
        if q in symbol.lower() or q in zh or q in en.lower() or any(q in a.lower() for a in also)
    ]


def _currencies(query: str) -> list[PublicSecurity]:
    """Currencies with a chart against the New Taiwan dollar whose code or name has ``query``
    in it (D-072): 歐元, EUR or euro find ``EURTWD``."""
    q = query.strip().lower()
    found = [
        PublicSecurity(
            symbol=f"{code}TWD", market="market", name=zh, name_en=en, exchange="Tiingo", kind="fx"
        )
        for code, zh, en in currencies.CURRENCIES
        if code in currencies.CHARTED and (q in code.lower() or q in zh or q in en.lower())
    ]
    # a grain (D-080): its world price, and the fund that holds its futures
    for key, (_, zh, en, fund) in GRAINS.items():
        if q in zh or q in en.lower() or q == fund.lower():
            found.append(
                PublicSecurity(
                    symbol=key.upper(),
                    market="market",
                    name=zh,
                    name_en=en,
                    exchange="IMF",
                    kind="commodity",
                )  # fmt: skip
            )
    return found


@router.get("/api/public/securities")
async def search_securities(
    session: Session,
    response: Response,
    q: Annotated[str, Query(min_length=1, max_length=40)],
    limit: Annotated[int, Query(ge=1, le=20)] = 12,
) -> list[PublicSecurity]:
    """Any listed Taiwan or US stock (D-061), by code, ticker or name; a currency against the
    New Taiwan dollar (D-072), by its name or code — ``EURTWD``, market ``market``, kind ``fx``;
    and the strip's own figures (D-189): the index, 台指期, rates, oil, gold, coins."""
    response.headers["Cache-Control"] = "public, max-age=3600"
    return (
        _figures(q)
        + _currencies(q)
        + [
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
    )


@router.get("/api/public/quotes")
async def get_quotes(
    session: Session,
    board: Annotated[QuoteBoard, Depends(market_board)],
    keys: Annotated[str, Query(max_length=2000, description="tw:2330,us:PLTR — at most 60")],
    forex: Annotated[TiingoFx, Depends(forex_cache)],
    fred: Annotated[FredHistory, Depends(fred_history)],
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
        # a grain's world price (D-080): its last month, against the month before
        if key in GRAINS and (figure := await Figures(forex, fred).figure(key)) is not None:
            out.append(
                PublicQuote(
                    key=key,
                    value=figure.value,
                    change=figure.change,
                    change_pct=None if figure.change_pct is None else round(figure.change_pct, 2),
                    as_of=figure.as_of,
                    basis="month",
                    source=figure.source,
                    currency="USD",
                )
            )
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
