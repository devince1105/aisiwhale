"""What the public site reads and records (T-515; platform/05 §4, §8; 3d-office/06 §2).

The site shows only what was published: the draft group the publisher marked as published
(``Article.published_group_id``), in the languages it was published in. Readers see the text and
the sources behind it (the evidence the cited claims quote: title, site and link), never the
claims' internals, drafts or anything unpublished.

Some articles are for members (D-025), shown as VIP (D-159); and the holdings sections are for
signed-in readers, free (D-159). The paywall lives here, in what is returned: a reader who may
read it gets the whole article, anybody else gets the opening (``PREVIEW_BLOCKS``), ``locked``
and which lock (``lock``: ``members`` or ``sign_in``). The site never receives the rest of the
text and then hides it — a reader with the developer tools open would find it there. Who the
reader is is decided above this module: this one is handed ``anyone``, ``signed_in``,
``member``, ``paid`` (has unlocked this COIN article) or ``staff`` (an admin).

A COIN article (P4, D-249) is read for Whale Coins, each reader paying once: being VIP does not
open it, and in a 持股觀察 section neither does signing in — its price, ``coin_price``, is on
every list, so the site can say what it costs before anybody opens it.

Beacons (``record_beacon``) count readers without knowing who they are: the browser sends a
random id it makes each day (``session_hash``); no IP address or anything else about the reader is
stored. One count per session, article, language, kind and day: repeats are dropped.

The site is in sections (D-047): big investors' filings, public figures' holdings (D-050), AI
and tech, Taiwan stocks, US stocks, crypto, institutions' market views (D-057), gold, the other
commodities and foreign exchange (D-067). An article's
section is not stored — it is its story's, which is the section most of the story's items'
sources name (``config.section``).
Retagging a source moves what is already written.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta, timezone
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel
from sqlalchemy import Date, Text, cast, func, or_, select, tuple_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from autora.db.models import Company
from autora.domains.newsroom.covers import cover_of
from autora.domains.newsroom.figures import figures_named
from autora.domains.newsroom.holdings import stocks_named
from autora.domains.newsroom.models import (
    AnalyticsEvent,
    AnalyticsEventType,
    Article,
    ArticleAccess,
    ArticleVersion,
    ClaimEvidence,
    CoverState,
    Evidence,
    Source,
    SourceItem,
    Story,
    StoryCover,
    StoryItem,
    SupportType,
)
from autora.domains.newsroom.publisher import article_path
from autora.domains.newsroom.sources import SECTION, SECTION_GUESS, SECTIONS
from autora.infra.ids import uuid7

MAX_LIST = 50
PREVIEW_BLOCKS = 2
"""At most how many blocks of a locked article anybody may read."""

SIGN_IN_SECTIONS = frozenset({"holdings", "figures", "institutions"})
"""持股觀察 (D-159): big investors' filings, public figures' holdings and — since 機構觀點 moved
under it (10/06, the site's operator's decision) — the asset managers' published views are read
in full once signed in: free, but an account; the reader's email is what the section is for."""

Reader = Literal["anyone", "signed_in", "member", "paid", "staff"]
Lock = Literal["members", "sign_in", "coin"]


def lock_for(access: str, section: str | None) -> Lock | None:
    """What it takes to read the whole article: coins, a membership, signing in, or nothing.
    COIN comes first: a 持股觀察 article set to COIN is paid for, not just signed in to."""
    if access == ArticleAccess.COIN.value:
        return "coin"
    if access == ArticleAccess.MEMBERS.value:
        return "members"
    if section in SIGN_IN_SECTIONS:
        return "sign_in"
    return None


def may_read(lock: Lock | None, reader: Reader) -> bool:
    if lock is None or reader == "staff":
        return True
    if lock == "coin":
        return reader == "paid"  # a membership does not open it (D-249)
    if reader == "member":
        return True
    return lock == "sign_in" and reader == "signed_in"


def preview(body: list[dict]) -> list[dict]:
    """The opening of a locked article — always strictly less than all of it.

    A short article would otherwise be given away whole: two blocks of a two-block piece is
    the piece. What stays behind is at least the last block, whatever the length."""
    return body[: min(PREVIEW_BLOCKS, max(0, len(body) - 1))]


class PublicBlock(BaseModel):
    type: str
    text: str


class PublicSource(BaseModel):
    title: str
    site: str
    url: str


class PublicNamedStock(BaseModel):
    """A stock an article names (D-077): its strip key, and its name in the article's language."""

    key: str
    symbol: str
    name: str


class PublicCover(BaseModel):
    """The article's cover photo (D-142): 1200x630 WebP, and whose it is."""

    url: str
    width: int
    height: int
    alt: str
    credit: str
    """The photographer, as the library names them."""
    library: str
    page_url: str
    """The photo's page at the library: the credit links there."""


LIBRARY_NAME = {"pixabay": "Pixabay", "pexels": "Pexels", "gemini": ""}
"""A generated cover (D-145) names no library: its credit says what it is."""


def public_cover(row: StoryCover | None, lang: str) -> PublicCover | None:
    if row is None or row.state != CoverState.ACTIVE:
        return None
    alt = row.alt.get(lang) or row.alt.get("en") or ""
    return PublicCover(
        url=row.url,
        width=row.width,
        height=row.height,
        alt=str(alt),
        credit=row.credit,
        library=LIBRARY_NAME.get(row.provider, row.provider),
        page_url=row.page_url,
    )


async def _covers(session: AsyncSession, story_ids: list[uuid.UUID]) -> dict[uuid.UUID, StoryCover]:
    if not story_ids:
        return {}
    rows = await session.scalars(select(StoryCover).where(StoryCover.story_id.in_(story_ids)))
    return {row.story_id: row for row in rows}


class PublicArticleSummary(BaseModel):
    article_id: uuid.UUID
    lang: str
    slug: str
    path: str
    title: str
    summary: str | None
    published_at: datetime
    revised_at: datetime | None = None
    """When a changed version went up (D-045); the page says so, as a correction should."""
    access: str = ArticleAccess.FREE.value
    """``free``, ``members`` (D-025) or ``coin`` (D-249). On a list, this draws the badge."""
    coin_price: int | None = None
    """A COIN article's price in coins; None for any other."""
    section: str | None = None
    """One of ``SECTIONS`` (D-047), or None when none of its story's sources names one."""
    cover: PublicCover | None = None
    stocks: list[PublicNamedStock] = []
    """What it names that has a chart, for quick links to it on the watchlist page: a 台股 or
    美股 story's stocks (D-077, D-078), a crypto, gold, futures or FX story's figures (D-079)."""


class PublicNeighbour(BaseModel):
    """The next article along, newer or older, in the same language and company."""

    title: str
    path: str


class PublicArticle(PublicArticleSummary):
    locked: bool = False
    """True when ``blocks`` is only the opening, because of ``lock``."""
    lock: Lock | None = None
    """What reading all of it takes (D-159): ``members`` (VIP), ``sign_in`` or ``coin``
    (D-249); None when free."""
    unlocked: bool = False
    """A COIN article this reader paid for: the whole of it, because they did."""
    blocks: list[PublicBlock]
    sources: list[PublicSource]
    """The evidence the article's claims quote, once per page, in order of first use."""
    langs: dict[str, str]
    """Every published language -> its page, for the language switch and hreflang."""
    company: str
    company_id: uuid.UUID
    """Whose article it is — the site asks that company whether this reader is a member."""
    company_slug: str
    """The same company, as the public API names one. The paywall asks what a year costs here."""
    newer: PublicNeighbour | None = None
    older: PublicNeighbour | None = None


def _summary(
    article: Article,
    version: ArticleVersion,
    section: str | None,
    cover: StoryCover | None = None,
) -> PublicArticleSummary:
    assert article.published_at is not None
    return PublicArticleSummary(
        access=article.access,
        coin_price=article.coin_price,
        article_id=article.id,
        lang=version.lang,
        slug=article.slug,
        path=article_path(version.lang, article.slug),
        title=version.title,
        summary=version.summary,
        published_at=article.published_at,
        revised_at=article.revised_at,
        section=section,
        cover=public_cover(cover, version.lang),
        stocks=_named(version, section),
    )


async def _summaries(session: AsyncSession, rows) -> list[PublicArticleSummary]:
    covers = await _covers(session, [article.story_id for article, _, _ in rows])
    return [
        _summary(article, version, named, covers.get(article.story_id))
        for article, version, named in rows
    ]


STOCK_SECTIONS = ("tw", "us", "ai")
"""Where an article's stocks are linked (D-078): Taiwan and US stock news, and AI and tech news
— Microsoft's Copilot is Microsoft's (D-079). A 13F's or an institution's list of names is what
the article is, not a stock it is about."""


def _named(version: ArticleVersion, section: str | None) -> list[PublicNamedStock]:
    """What the version names that has a chart, in its language: a 台股 or 美股 story's stocks
    (D-077, D-078); a crypto, gold, futures or FX story's figures (D-079)."""
    said = " ".join([version.title, version.summary or "", *(b["text"] for b in version.body)])
    zh = version.lang.startswith("zh")
    stocks = (
        [
            PublicNamedStock(key=s.key, symbol=s.symbol, name=s.zh if zh else s.en)
            for s in stocks_named(said)
        ]
        if section in STOCK_SECTIONS
        else []
    )
    # and its figures: a stock story's index (the TAIEX, the Nasdaq, the yield), a crypto, gold,
    # futures or FX story's coins, gold, oil or currencies
    figures = [
        PublicNamedStock(
            key=key, symbol=key.split(":")[-1].upper(), name=name_zh if zh else name_en
        )
        for key, name_zh, name_en in figures_named(said, section)
    ]
    return (stocks + figures)[:8]


def _section():
    """The section a person gave the article's story (D-208), else the one most of its sources
    name — ties go to the first in alphabetical order, so an article does not change section from
    one read to the next — else the one its story's own words name (D-212).

    A story a person started — a brief from the team chat — has no sources at all, so without a
    section given it is on the front page only: 10/05's close of the TAIEX at a record was not
    under 台股."""
    named = Source.config[SECTION].astext
    by_sources = (
        select(named)
        .select_from(StoryItem)
        .join(SourceItem, SourceItem.id == StoryItem.source_item_id)
        .join(Source, Source.id == SourceItem.source_id)
        .where(StoryItem.story_id == Article.story_id, named.in_(SECTIONS))
        .group_by(named)
        .order_by(func.count().desc(), named)
        .limit(1)
        .correlate(Article)
        .scalar_subquery()
    )

    def from_seed(key: str):
        value = Story.seed[key].astext
        return (
            select(value)
            .where(Story.id == Article.story_id, value.in_(SECTIONS))
            .correlate(Article)
            .scalar_subquery()
        )

    # a person's choice, then the sources, then what the story's own words say (D-212)
    return func.coalesce(from_seed(SECTION), by_sources, from_seed(SECTION_GUESS))


async def section_of(session: AsyncSession, article_id: uuid.UUID) -> str | None:
    """The section an article is in on the site (D-047, D-208)."""
    return await session.scalar(
        select(_section()).select_from(Article).where(Article.id == article_id)
    )


def _published(lang: str):
    """Published articles with their version in ``lang`` (only if published in that language).

    On the site is "has a published version and is listed" (D-045), not "is PUBLISHED": an
    article being revised keeps showing what was published until the new version is."""
    return (
        select(Article, ArticleVersion, _section())
        .join(ArticleVersion, ArticleVersion.draft_group_id == Article.published_group_id)
        .where(
            Article.published_group_id.is_not(None),
            Article.listed.is_(True),
            ArticleVersion.lang == lang,
            Article.published_langs.any(lang),
        )
    )


async def published_article(
    session: AsyncSession, lang: str, slug: str, *, reader: Reader = "anyone"
) -> PublicArticle | None:
    """One published article, as much of it as ``reader`` may read: a locked one comes back as
    its opening, ``locked``, with its ``lock``."""
    row = (await session.execute(_published(lang).where(Article.slug == slug))).first()
    if row is None:
        return None
    article, version, section = row
    company = await session.get(Company, article.company_id)
    cited: list[uuid.UUID] = []
    for block in version.body:
        for claim_id in block.get("claim_ids", []):
            if uuid.UUID(claim_id) not in cited:
                cited.append(uuid.UUID(claim_id))
    evidence = (
        await session.execute(
            select(ClaimEvidence.claim_id, Evidence.url, Evidence.title)
            .join(Evidence, Evidence.id == ClaimEvidence.evidence_id)
            .where(
                ClaimEvidence.claim_id.in_(cited),
                ClaimEvidence.support_type == SupportType.SUPPORTS,
            )
        )
    ).all()
    by_claim: dict[uuid.UUID, list[tuple[str, str | None]]] = {}
    for claim_id, url, title in evidence:
        by_claim.setdefault(claim_id, []).append((url, title))
    sources: dict[str, PublicSource] = {}
    for claim_id in cited:
        for url, title in sorted(by_claim.get(claim_id, [])):
            if url not in sources:
                site = urlsplit(url).hostname or url
                sources[url] = PublicSource(title=title or site, site=site, url=url)
    lock = lock_for(article.access, section)
    locked = not may_read(lock, reader)
    body = preview(version.body) if locked else version.body
    newer, older = await _neighbours(session, lang, article)
    return PublicArticle(
        **_summary(
            article, version, section, await cover_of(session, article.story_id)
        ).model_dump(),
        locked=locked,
        lock=lock,
        unlocked=lock == "coin" and reader == "paid",
        blocks=[PublicBlock(type=b["type"], text=b["text"]) for b in body],
        sources=[] if locked else list(sources.values()),
        langs={lang_: article_path(lang_, article.slug) for lang_ in article.published_langs},
        company=company.name if company else "",
        company_id=article.company_id,
        company_slug=company.slug if company else "",
        newer=newer,
        older=older,
    )


async def _neighbours(
    session: AsyncSession, lang: str, article: Article
) -> tuple[PublicNeighbour | None, PublicNeighbour | None]:
    """The article published just after this one and the one just before, as the list orders
    them (newest first), among the same company's articles on the site in this language."""
    here = tuple_(Article.published_at, Article.id)
    at = tuple_(article.published_at, article.id)
    mine = _published(lang).where(Article.company_id == article.company_id)
    out: list[PublicNeighbour | None] = []
    for query in (
        mine.where(here > at).order_by(Article.published_at.asc(), Article.id.asc()),
        mine.where(here < at).order_by(Article.published_at.desc(), Article.id.desc()),
    ):
        row = (await session.execute(query.limit(1))).first()
        out.append(
            None
            if row is None
            else PublicNeighbour(title=row[1].title, path=article_path(lang, row[0].slug))
        )
    return out[0], out[1]


async def published_articles(
    session: AsyncSession,
    lang: str,
    *,
    company_slug: str | None = None,
    section: str | list[str] | None = None,
    limit: int = 20,
    offset: int = 0,
    day: date | None = None,
) -> list[PublicArticleSummary]:
    """Newest first. ``offset`` pages through them; a page that comes back shorter than
    ``limit`` is the last. ``section`` may be several: the site's 持股觀察 (holdings watch) is the
    big investors' and the public figures' together (D-050). ``day``: only that day's, in
    Taipei (D-084)."""
    query = _listed(lang, company_slug, section, day).order_by(
        Article.published_at.desc(), Article.id.desc()
    )
    query = query.limit(min(max(limit, 1), MAX_LIST)).offset(max(offset, 0))
    rows = (await session.execute(query)).all()
    return await _summaries(session, rows)


async def count_published_articles(
    session: AsyncSession,
    lang: str,
    *,
    company_slug: str | None = None,
    section: str | list[str] | None = None,
    day: date | None = None,
) -> int:
    """How many ``published_articles`` pages through, all told: a list's page numbers."""
    listed = _listed(lang, company_slug, section, day).subquery()
    return int(await session.scalar(select(func.count()).select_from(listed)) or 0)


TAIPEI = timezone(timedelta(hours=8))
"""The site's day (D-084): a story published at 23:30 in Taipei is that day's, whatever UTC says."""


def _taipei_day(day: date) -> tuple[datetime, datetime]:
    start = datetime(day.year, day.month, day.day, tzinfo=TAIPEI)
    return start, start + timedelta(days=1)


def _listed(
    lang: str,
    company_slug: str | None,
    section: str | list[str] | None,
    day: date | None = None,
):
    query = _published(lang)
    if company_slug is not None:
        query = query.join(Company, Company.id == Article.company_id).where(
            Company.slug == company_slug
        )
    if section:
        sections = [section] if isinstance(section, str) else list(section)
        query = query.where(_section().in_(sections))
    if day is not None:
        start, end = _taipei_day(day)
        query = query.where(Article.published_at >= start, Article.published_at < end)
    return query


POPULAR_DAYS = 7
"""How far back 熱門文章 counts (D-086): a week's reads, so last month's hit makes way."""


async def popular_articles(
    session: AsyncSession,
    lang: str,
    *,
    company_slug: str | None = None,
    limit: int = 5,
    now: datetime | None = None,
) -> list[PublicArticleSummary]:
    """The most read of the site's published articles in ``lang`` over the last ``POPULAR_DAYS``
    (D-086): opened pages, one a reader a day (the beacon's own dedup), the newer first on a tie.
    None read yet: none."""
    since = (now or datetime.now(UTC)) - timedelta(days=POPULAR_DAYS)
    views = (
        select(AnalyticsEvent.article_id, func.count().label("views"))
        .where(
            AnalyticsEvent.event_type == AnalyticsEventType.VIEW.value,
            AnalyticsEvent.lang == lang,
            AnalyticsEvent.created_at >= since,
        )
        .group_by(AnalyticsEvent.article_id)
        .subquery()
    )
    query = (
        _listed(lang, company_slug, None)
        .join(views, views.c.article_id == Article.id)
        .order_by(views.c.views.desc(), Article.published_at.desc())
        .limit(min(max(limit, 1), 10))
    )
    rows = (await session.execute(query)).all()
    return await _summaries(session, rows)


class PublicDay(BaseModel):
    day: date
    count: int


async def published_days(
    session: AsyncSession,
    lang: str,
    month: date,
    *,
    company_slug: str | None = None,
    section: str | list[str] | None = None,
) -> list[PublicDay]:
    """The days of ``month`` (Taipei's) with published articles, and how many each (D-084): the
    calendar marks them, and only they are a link."""
    first = month.replace(day=1)
    after = (first + timedelta(days=32)).replace(day=1)
    start, _ = _taipei_day(first)
    end, _ = _taipei_day(after)
    local = cast(func.timezone("Asia/Taipei", Article.published_at), Date)
    query = (
        _listed(lang, company_slug, section)
        .where(Article.published_at >= start, Article.published_at < end)
        .with_only_columns(local, func.count(), maintain_column_froms=True)
        .group_by(local)
        .order_by(local)
    )
    return [PublicDay(day=day, count=count) for day, count in (await session.execute(query)).all()]


async def published_articles_mentioning(
    session: AsyncSession,
    lang: str,
    terms: tuple[str, ...],
    *,
    company_slug: str | None = None,
    limit: int = 10,
    offset: int = 0,
) -> list[PublicArticleSummary]:
    """The newest published articles in ``lang`` whose title, summary or text names any of
    ``terms`` (D-049, a stock page's "our coverage"). A Latin term matches as a whole word and
    in its own case — ``MU`` is not in "MUST", ``Meta`` is not "metadata" — others anywhere.
    ``offset`` pages through them (D-066)."""
    query = _mentioning(lang, terms, company_slug)
    if query is None:
        return []
    query = (
        query.order_by(Article.published_at.desc(), Article.id.desc())
        .limit(min(max(limit, 1), MAX_LIST))
        .offset(max(offset, 0))
    )
    rows = (await session.execute(query)).all()
    return await _summaries(session, rows)


async def count_articles_mentioning(
    session: AsyncSession,
    lang: str,
    terms: tuple[str, ...],
    *,
    company_slug: str | None = None,
) -> int:
    """How many ``published_articles_mentioning`` pages through, all told."""
    query = _mentioning(lang, terms, company_slug)
    if query is None:
        return 0
    return int(await session.scalar(select(func.count()).select_from(query.subquery())) or 0)


def _mentioning(lang: str, terms: tuple[str, ...], company_slug: str | None):
    text_of = func.concat_ws(
        " ", ArticleVersion.title, ArticleVersion.summary, cast(ArticleVersion.body, Text)
    )
    matches = []
    for term in terms:
        if term.isascii():
            matches.append(text_of.op("~")(rf"\m{re.escape(term)}\M"))
        else:
            matches.append(text_of.contains(term, autoescape=True))
    if not matches:
        return None
    query = _published(lang).where(or_(*matches))
    if company_slug is not None:
        query = query.join(Company, Company.id == Article.company_id).where(
            Company.slug == company_slug
        )
    return query


class BeaconRejected(Exception):
    """The beacon is not about a published article in that language."""


@dataclass(frozen=True)
class BeaconOutcome:
    recorded: bool
    """False when this session had already counted (a repeat is dropped)."""


async def record_beacon(
    session: AsyncSession,
    *,
    article_id: uuid.UUID,
    lang: str,
    event_type: AnalyticsEventType,
    session_hash: str,
    now: datetime | None = None,
) -> BeaconOutcome:
    article = await session.get(Article, article_id)
    if (
        article is None
        or article.published_group_id is None
        or not article.listed
        or lang not in article.published_langs
    ):
        raise BeaconRejected(f"no published article {article_id} in {lang}")
    day: date = (now or datetime.now(UTC)).astimezone(UTC).date()
    result = await session.execute(
        insert(AnalyticsEvent)
        .values(
            id=uuid7(),
            company_id=article.company_id,
            article_id=article.id,
            lang=lang,
            event_type=event_type.value,
            session_hash=session_hash,
            day=day,
        )
        .on_conflict_do_nothing()
        .returning(AnalyticsEvent.id)
    )
    return BeaconOutcome(recorded=result.scalar_one_or_none() is not None)
