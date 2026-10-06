"""The investing newsroom (D-035, D-036): the company the public site is really for.

What it covers: US and Taiwan stocks, the AI and technology industry, and personal investing —
led by "what the big investors hold", in Chinese, each story linked to the filing it reports.
It reports facts and what others said, never its own advice (``newsroom.no_advice``, on here).

Its sources, and why each is set up the way it is:

- **13F filings** of five investors, from SEC EDGAR's own Atom feed per filer. Every entry is
  titled the same ("13F-HR - Quarterly report ..."), so each source prefixes the investor's name
  (``title_prefix``), every filing is a story of its own (``own_story``) and needs no second
  source to rank (``primary``, the filing is the record): this quarter's
  filing looks exactly like last quarter's and must not join the story already written. Only
  filings of the last 120 days are taken on the first poll (``max_age_days``), not the ten years
  of history the feed lists. A 13F is due 45 days after the quarter, so these arrive four times a
  year each; polling twice a day is plenty. SEC answers only requests that name a contact
  (``FETCH_CONTACT_EMAIL``).
- **AI companies' press releases** (NVIDIA, OpenAI, Google AI, Microsoft), whose feeds answer
  automated readers. TSMC's refuses them (403) and Anthropic has none; AMD's timed out when tried.
- **Searches** for Taiwan's market and the AI supply chain, which have no feed a program may read.
  Each search costs a Tavily credit, so they run twice a day: three searches, about 180 credits
  a month of the free plan's 1,000, leaving the rest for the researcher's own searches.
- **機構觀點** (D-057): what the ten largest asset managers publish about the markets — their own
  free outlooks and commentaries, reported as theirs ("貝萊德表示…"), never as the site's advice.
  Ten firms in two searches, once a day over a week of results: about 60 credits a month.
- **證交所重大訊息** (D-169): the exchange's own record of what listed companies announce —
  the AI supply chain's and the largest companies' announcements whatever they are about, and
  anyone's take-over, merger or buy-back. Free, every two hours (the dataset is the latest
  trading day's), the record itself (``primary``).
- **GDELT** (D-169): English news worldwide, free and without credits — Taiwan's tech industry
  as reported from Taiwan, and the AI chip race on a few news sites whose pages can be read.
  Only in English: a query in Chinese finds English pages that GDELT translated, not 中文 news.

Scion Asset Management (Michael Burry) is on the list the user chose, but its last 13F was filed
on 2025-11-03: it may never produce another story. Kept, because a filing would be news.

Nothing here works in fixture mode: the sources are the real web (``TOOLS_PROFILE=live``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from autora.company.agents.roster import hire_agent
from autora.company.companies import create_company
from autora.company.organization import bootstrap_executive, business_unit_by_key
from autora.db.models import Agent, Company, Project, ProjectState
from autora.db.repositories.companies import get_company_by_slug, get_policies, upsert_policy
from autora.domains.newsroom import forex, institutions, personas
from autora.domains.newsroom import organization as newsroom_org
from autora.domains.newsroom.advice import NO_ADVICE_KEY
from autora.domains.newsroom.models import Source, SourceStatus
from autora.domains.newsroom.sources import (
    MATCH_HOURS,
    MAX_AGE_DAYS,
    OWN_STORY,
    PRIMARY,
    SECTION,
    TITLE_PREFIX,
    add_source,
    ensure_newsroom_schedules,
)
from autora.domains.newsroom.tools.filings import PREDECESSORS
from autora.domains.newsroom.workflow import staff_newsroom
from autora.runtime.actor import Actor

SLUG = "aisiwhale"  # was autora-finance (renamed 2026-10-01, D-154)
NAME = "艾矽鯨"
"""AiSiWhale (D-043): 艾 (ài, as in AI), 矽 = silicon, 鯨 = the whales whose holdings it follows."""
PROJECT = "持股動態與科技產業"
MISSION = (
    "用附原始出處的中英雙語報導，追蹤 AI 與半導體產業的動向、大型投資人的持股變化，"
    "台股、美股裡的 AI 科技公司，名人（如美國總統、國會議員）依法申報的持股與交易，"
    "加密貨幣的監管、ETF 與市場動態，"
    "以及黃金、期貨（金屬、能源、農產品）與外匯（臺灣銀行掛牌的外幣）的價格與供需；"
    "只報導事實與別人說的話，不提供投資建議。"
)

HALF_DAY = 12 * 3600
DAY = 24 * 3600


def edgar_13f(cik: str) -> str:
    """SEC's Atom feed of one filer's 13F-HR filings, newest first."""
    return (
        "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany"
        f"&CIK={cik}&type=13F-HR&dateb=&owner=include&count=10&output=atom"
    )


@dataclass(frozen=True)
class MarketSource:
    name: str
    kind: str
    trust_level: Decimal
    language: str
    url: str | None = None
    config: dict[str, Any] = field(default_factory=dict)
    poll_interval_seconds: int = 3600


def _investor(
    name: str, filer: str, cik: str, *, predecessors: tuple[str, ...] = ()
) -> MarketSource:
    config: dict[str, Any] = {
        TITLE_PREFIX: f"{name}（{filer}）",
        OWN_STORY: True,
        PRIMARY: True,
        MAX_AGE_DAYS: 120,
        SECTION: "holdings",
    }
    if predecessors:
        config[PREDECESSORS] = list(predecessors)
    return MarketSource(
        name=f"SEC 13F：{name}",
        kind="rss",
        url=edgar_13f(cik),
        trust_level=Decimal("0.95"),
        language="en",
        config=config,
        poll_interval_seconds=HALF_DAY,
    )


def _press(name: str, url: str, section: str = "ai") -> MarketSource:
    return MarketSource(
        name=name,
        kind="rss",
        url=url,
        trust_level=Decimal("0.8"),
        language="en",
        config={MAX_AGE_DAYS: 7, SECTION: section},
    )


def edgar_filings(cik: str) -> str:
    """SEC's Atom feed of every filing a person is named in as the reporting owner (Forms 3, 4,
    5; Schedule 13D/G), newest first."""
    return (
        "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany"
        f"&CIK={cik}&type=&dateb=&owner=include&count=10&output=atom"
    )


def _figure(name: str, cik: str) -> MarketSource:
    """A public figure's own SEC filings as an owner (D-050): what they bought, sold or hold in
    a listed company, in their own filings. Every filing is its own story, like a 13F."""
    return MarketSource(
        name=f"SEC 申報：{name}",
        kind="rss",
        url=edgar_filings(cik),
        trust_level=Decimal("0.95"),
        language="en",
        config={
            TITLE_PREFIX: name,
            OWN_STORY: True,
            PRIMARY: True,
            MAX_AGE_DAYS: 120,
            SECTION: "figures",
        },
        poll_interval_seconds=HALF_DAY,
    )


PRICE_BEATS = ("gold", "commodities", "fx")
"""Sections whose news is a price, every day (D-067)."""


def _search(
    query: str,
    section: str,
    language: str = "zh-TW",
    *,
    recency_days: int = 2,
    every: int = HALF_DAY,
    domains: tuple[str, ...] = (),
    name: str | None = None,
) -> MarketSource:
    config: dict[str, Any] = {
        "query": query,
        "k": 5,
        "recency_days": recency_days,
        SECTION: section,
    }
    if domains:
        config["domains"] = list(domains)
    if section in PRICE_BEATS:
        config[MATCH_HOURS] = 12  # each day's close is its own story
    return MarketSource(
        name=f"搜尋：{name or query}",
        kind="search_query",
        trust_level=Decimal("0.5"),
        language=language,
        config=config,
        poll_interval_seconds=every,
    )


INSTITUTIONS_A = institutions.domains("blackrock", "vanguard", "fidelity", "ubs", "state_street")
"""Where BlackRock, Vanguard, Fidelity, UBS and State Street publish their outlooks."""
INSTITUTIONS_B = institutions.domains("jpmorgan", "goldman", "capital_group", "amundi", "bny")
"""J.P. Morgan, Goldman Sachs, Capital Group, Amundi (Crédit Agricole's asset manager) and BNY."""

TW_NEWS = (
    "cna.com.tw",
    "cnyes.com",
    "money.udn.com",
    "ctee.com.tw",
    "moneydj.com",
    "ec.ltn.com.tw",
)
"""Taiwan's financial news: 中央社, 鉅亨, 經濟日報, 工商時報, MoneyDJ, 自由財經 (D-067)."""
COMMODITY_NEWS = ("reuters.com", "kitco.com", "mining.com", "spglobal.com", "iea.org")
"""Commodity news and data in English: Reuters, Kitco, Mining.com, S&P Global, the IEA."""

TWSE_WATCH = (
    *("2330", "2317", "2454", "2382", "2308"),  # the market strip's (TW_STOCKS)
    *("3231", "6669", "2357", "2376", "3711", "2303", "2345", "3017", "3661", "3443", "2395"),
    *("2412", "2881", "2882", "2891"),
)
"""Companies whose every announcement is taken: the AI supply chain (緯創, 緯穎, 華碩, 技嘉,
日月光投控, 聯電, 智邦, 奇鋐, 世芯-KY, 創意, 研華) and the largest (中華電, 富邦金, 國泰金,
中信金)."""
TWSE_EVENTS = (
    *("公開收購", "併購", "吸收合併", "合併契約", "合併基準日", "股份轉換"),
    *("買回本公司股份", "庫藏股", "下市"),
)
"""Announcements taken from any listed company: who is buying whom, and who buys back its own.
Not 「合併」 alone: every monthly revenue report is 「合併營收」."""


def _gdelt(name: str, query: str, section: str) -> MarketSource:
    return MarketSource(
        name=f"GDELT：{name}",
        kind="gdelt",
        trust_level=Decimal("0.5"),
        language="en",
        config={"query": query, "timespan": "6h", "maxrecords": 20, SECTION: section},
        poll_interval_seconds=3 * 3600,
    )


GDELT_READABLE = (
    "cnbc.com",
    "apnews.com",
    "techcrunch.com",
    "theverge.com",
    "tomshardware.com",
    "theregister.com",
    "focustaiwan.tw",
)
"""News sites whose articles a program can read (no paywall)."""

SOURCES: tuple[MarketSource, ...] = (
    _investor("巴菲特", "Berkshire Hathaway", "0001067983"),
    # Pershing Square Capital Management (CIK 1336528) filed only a 13F-NT for 2026-06-30: its
    # holdings are reported by Pershing Square Inc. (CIK 2026053) from then on, so the previous
    # quarter adds up both entities' filings
    _investor("比爾・艾克曼", "Pershing Square", "0002026053", predecessors=("1336528",)),
    _investor("麥可・貝瑞", "Scion Asset Management", "0001649339"),
    _investor("杜肯米勒", "Duquesne Family Office", "0001536411"),
    _investor("段永平", "H&H International Investment", "0001759760"),
    _investor("木頭姐", "ARK Investment Management", "0001697748"),
    # the holdings dashboard's (HD-01): NVIDIA's own investments — the company's, not its CEO's —
    # Singapore's state investor, and Soros's family office
    _investor("輝達", "NVIDIA", "0001045810"),
    _investor("淡馬錫", "Temasek", "0001021944"),
    _investor("索羅斯", "Soros Fund Management", "0001029160"),
    # the big holders' tab, asked for 2026-10-06 (D-217): a macro fund, a charitable trust, a
    # China-focused manager, and Saudi Arabia's state fund
    _investor("橋水", "Bridgewater Associates", "0001350694"),
    _investor("蓋茲基金會", "Gates Foundation Trust", "0001166559"),
    _investor("高瓴", "HHLR Advisors", "0001762304"),
    _investor("沙烏地公共投資基金", "Public Investment Fund", "0001767640"),
    # public figures (D-050): the President's SEC filings as an owner (Trump Media, DJT), and —
    # as neither the President's OGE transaction reports nor Congress's STOCK Act reports have a
    # feed — searches for news of new ones, which the newsroom follows to the filing itself
    _figure("川普（Donald J. Trump）", "0000947033"),
    _search("Trump OGE 278-T periodic transaction report stocks bonds", "figures", "en"),
    _search("Pelosi periodic transaction report stock trades disclosure", "figures", "en"),
    MarketSource(
        name="證交所重大訊息",
        kind="twse_announcements",
        trust_level=Decimal("0.95"),
        language="zh-TW",
        config={
            "codes": list(TWSE_WATCH),
            "keywords": list(TWSE_EVENTS),
            PRIMARY: True,
            MAX_AGE_DAYS: 3,
            SECTION: "tw",
        },
        poll_interval_seconds=2 * 3600,
    ),
    _gdelt(
        "台灣科技業（英文報導）",
        '(TSMC OR Foxconn OR MediaTek OR Taiex OR "Taiwan stocks" OR semiconductor)'
        " sourcecountry:taiwan sourcelang:english",
        "tw",
    ),
    _gdelt(
        "AI 晶片與資料中心",
        '(Nvidia OR TSMC OR "AI chips" OR "data center") ('
        + " OR ".join(f"domainis:{d}" for d in GDELT_READABLE)
        + ") sourcelang:english",
        "ai",
    ),
    _press("NVIDIA Newsroom", "https://nvidianews.nvidia.com/releases.xml"),
    _press("OpenAI News", "https://openai.com/news/rss.xml"),
    _press("Google AI Blog", "https://blog.google/technology/ai/rss/"),
    _press("Microsoft Source", "https://news.microsoft.com/source/feed/"),
    _search("台股 AI 伺服器 供應鏈", "tw"),
    _search("台積電 營收 法說會", "tw"),
    _search("美股 科技股 財報", "us"),
    _press("CoinDesk", "https://www.coindesk.com/arc/outboundfeeds/rss/", "crypto"),
    _search("比特幣 以太幣 ETF 監管", "crypto"),
    # 機構觀點 (D-057): the ten largest asset managers' own published outlooks — a weekly
    # commentary is news for a week, so a day's search over seven days of results is enough.
    # Only on the firms' own sites: ten names in one open query found Quora, Instagram and a
    # regulator's PDF, not one outlook
    _search(
        "market outlook weekly commentary",
        "institutions",
        "en",
        recency_days=7,
        every=DAY,
        domains=INSTITUTIONS_A,
        name="機構觀點（貝萊德、先鋒、富達、瑞銀、道富）",
    ),
    _search(
        "market outlook weekly commentary",
        "institutions",
        "en",
        recency_days=7,
        every=DAY,
        domains=INSTITUTIONS_B,
        name="機構觀點（摩根大通、高盛、資本集團、Amundi、紐約梅隆）",
    ),
    # 黃金、原物料、外匯 (D-067). Gold twice a day, as the one most asked about; the rest once
    # a day — a price moves every day, but a day's news of it is enough. Only on news sites: an
    # open query for a price found quote pages, currency converters, Instagram and app listings
    _search("黃金 金價 國際金價 央行購金 黃金ETF", "gold", domains=TW_NEWS, name="黃金"),
    _search(
        "銅價 鋁價 白銀 鎳 金屬 價格 供需", "commodities", domains=TW_NEWS, name="原物料：金屬"
    ),
    _search(
        "copper aluminum demand AI data centers power grid",
        "commodities",
        "en",
        every=DAY,
        domains=COMMODITY_NEWS,
        name="原物料：AI 資料中心帶動的金屬需求",
    ),
    _search(
        "國際油價 原油 天然氣 OPEC",
        "commodities",
        every=DAY,
        domains=TW_NEWS,
        name="原物料：能源",
    ),
    _search(
        "黃豆 玉米 小麥 農產品 期貨 價格",
        "commodities",
        every=DAY,
        domains=TW_NEWS,
        name="原物料：農產品",
    ),
    # the currencies Bank of Taiwan posts rates for (FX_CURRENCIES), in four searches
    _search("新台幣 匯率 美元 央行", "fx", domains=TW_NEWS, name="外匯：新台幣與美元"),
    _search(
        "日圓 韓元 人民幣 港幣 匯率",
        "fx",
        every=DAY,
        domains=TW_NEWS,
        name="外匯：亞洲主要貨幣",
    ),
    _search(
        "歐元 英鎊 瑞士法郎 澳幣 紐幣 加幣 南非幣 瑞典幣 匯率",
        "fx",
        every=DAY,
        domains=TW_NEWS,
        name="外匯：歐美與大洋洲貨幣",
    ),
    _search(
        "新加坡幣 泰銖 馬來幣 印尼盾 越南盾 菲律賓披索 匯率",
        "fx",
        every=DAY,
        domains=TW_NEWS,
        name="外匯：東南亞貨幣",
    ),
)

FX_CURRENCIES = tuple(code for code, _, _ in forex.CURRENCIES)
"""The foreign currencies Bank of Taiwan posts rates for: what 外匯 covers (D-067)."""

RETIRED = (
    "搜尋：BlackRock Vanguard Fidelity UBS State Street market outlook commentary",
    "搜尋：J.P. Morgan Asset Management Goldman Sachs Capital Group Amundi BNY investment outlook",
)
"""Sources the code no longer defines: D-057's first two searches, which found no outlooks."""


@dataclass
class MarketsNewsroom:
    company: Company
    project: Project
    sources: list[Source]
    added: list[str]


async def seed_markets(
    session: AsyncSession, *, actor: Actor, slug: str = SLUG, name: str = NAME
) -> MarketsNewsroom:
    """The company, its desks, its project, its sources and its no-advice policy. Idempotent:
    run it again and what is missing is added, sources already there take the settings above,
    a name given later renames it, and the mission is brought up to date."""
    company = await get_company_by_slug(session, slug)
    if company is None:
        company, _ = await create_company(
            session, slug=slug, name=name, mission=MISSION, actor=actor
        )
    else:
        # a name given later renames it; the mission is the code's, which the desk chooses by
        company.name = name
        company.mission = MISSION
    if not (await get_policies(session, company.id)).get(NO_ADVICE_KEY):
        await upsert_policy(session, company.id, NO_ADVICE_KEY, True, updated_by=actor.as_json())

    _, ceo_role = await bootstrap_executive(session, company.id, actor=actor)
    if (
        await session.scalar(
            select(Agent.id).where(Agent.company_id == company.id, Agent.role == ceo_role.key)
        )
        is None
    ):
        await hire_agent(
            session,
            company_id=company.id,
            role=ceo_role.key,
            display_name=personas.CEO.name,
            description=personas.CEO.description,
            avatar_key=personas.CEO.avatar,
            actor=actor,
            position=ceo_role,
        )
    await staff_newsroom(session, company.id, actor=actor)
    unit = await business_unit_by_key(session, company.id, newsroom_org.BUSINESS_UNIT)
    project = await session.scalar(
        select(Project).where(Project.company_id == company.id, Project.name == PROJECT)
    )
    if project is None:
        project = Project(
            company_id=company.id,
            business_unit_id=unit.id if unit else None,
            name=PROJECT,
            state=ProjectState.ACTIVE.value,
            kill_criteria={"max_cost_usd": 5},
        )
        session.add(project)
        await session.flush()

    existing = (await session.scalars(select(Source).where(Source.company_id == company.id))).all()
    known = {s.name: s for s in existing}  # a company's source names are unique
    added: list[str] = []
    for spec in SOURCES:
        if (source := known.get(spec.name)) is not None:
            # what the code says a source is wins: a setting added later, or a filer that moved
            # (Pershing Square), reaches the source already there, and keeps its history
            source.url = spec.url
            source.config = dict(spec.config)
            source.trust_level = spec.trust_level
            source.poll_interval_seconds = spec.poll_interval_seconds
            continue
        await add_source(
            session,
            company_id=company.id,
            name=spec.name,
            kind=spec.kind,
            url=spec.url,
            config=spec.config,
            trust_level=spec.trust_level,
            language=spec.language,
            poll_interval_seconds=spec.poll_interval_seconds,
        )
        added.append(spec.name)
    for name in RETIRED:  # replaced by a better source; paused, not deleted: its items stay
        if (source := known.get(name)) is not None:
            source.status = SourceStatus.PAUSED.value
    # the schedules too: one added later (the 13F positions, D-049) reaches a company seeded before
    await ensure_newsroom_schedules(session, company.id)
    sources = (await session.scalars(select(Source).where(Source.company_id == company.id))).all()
    return MarketsNewsroom(company=company, project=project, sources=list(sources), added=added)
