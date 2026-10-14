"""D-036: the investing newsroom — its sources, its no-advice policy, and seeding it twice."""

import uuid

from sqlalchemy import select

from autora.db.repositories.companies import get_policies, upsert_policy
from autora.domains.newsroom import holdings, markets
from autora.domains.newsroom.advice import NO_ADVICE_KEY
from autora.domains.newsroom.models import Source
from autora.domains.newsroom.policy import TOPIC_MIX_KEY
from autora.domains.newsroom.sources import SECTIONS, SourceConfigError, add_source
from autora.runtime.actor import Actor

ACTOR = Actor.human("test")


async def test_seeded_once_with_advice_off_limits_and_twice_without_duplicates(db_session):
    slug = f"markets-{uuid.uuid4().hex[:8]}"
    first = await markets.seed_markets(db_session, actor=ACTOR, slug=slug)
    assert first.company.name == markets.NAME
    assert (await get_policies(db_session, first.company.id))[NO_ADVICE_KEY] is True
    assert len(first.sources) == len(markets.SOURCES) == len(first.added)

    again = await markets.seed_markets(db_session, actor=ACTOR, slug=slug, name="新的名字")
    assert again.added == [] and len(again.sources) == len(markets.SOURCES)
    assert again.company.id == first.company.id and again.company.name == "新的名字"

    first.company.mission = "an old mission"
    await markets.seed_markets(db_session, actor=ACTOR, slug=slug)
    assert first.company.mission == markets.MISSION, "the desk chooses by today's mission"


async def test_every_filing_source_says_whose_it_is_and_stands_alone(db_session):
    newsroom = await markets.seed_markets(
        db_session, actor=ACTOR, slug=f"markets-{uuid.uuid4().hex[:8]}"
    )
    filings = (
        await db_session.scalars(
            select(Source).where(
                Source.company_id == newsroom.company.id, Source.url.contains("13F-HR")
            )
        )
    ).all()
    # Buffett, Ackman, Burry, Druckenmiller, Duan, Cathie Wood; NVIDIA, Temasek, Soros (HD-01);
    # Bridgewater, the Gates Foundation, Hillhouse and Saudi Arabia's PIF (the big holders' tab)
    assert len(filings) == 13
    # and a public figure's own filings as an owner (D-050)
    filings += (
        await db_session.scalars(
            select(Source).where(
                Source.company_id == newsroom.company.id, Source.url.contains("CIK=0000947033")
            )
        )
    ).all()
    assert len(filings) == 14 and filings[-1].config["section"] == "figures"
    for source in filings:
        assert source.config["own_story"] is True and source.config["max_age_days"] == 120
        assert source.config["title_prefix"] and source.trust_level >= 0.9


def test_the_13f_feed_is_sec_s_own():
    url = markets.edgar_13f("0001067983")
    assert url.startswith("https://www.sec.gov/cgi-bin/browse-edgar?")
    assert "CIK=0001067983" in url and "type=13F-HR" in url and "output=atom" in url


async def test_seeding_again_brings_old_sources_up_to_date(db_session):
    slug = f"markets-{uuid.uuid4().hex[:8]}"
    newsroom = await markets.seed_markets(db_session, actor=ACTOR, slug=slug)
    buffett = next(s for s in newsroom.sources if "巴菲特" in s.name)
    buffett.config = {"title_prefix": "old"}  # a source made before a setting existed
    await db_session.flush()

    await markets.seed_markets(db_session, actor=ACTOR, slug=slug)
    await db_session.refresh(buffett)
    assert buffett.config["primary"] is True and buffett.config["title_prefix"].startswith("巴菲特")


async def test_a_filer_that_moved_is_the_same_source_with_a_new_address(db_session):
    """Ackman's holdings moved to Pershing Square Inc.: the source follows, its history stays."""
    slug = f"markets-{uuid.uuid4().hex[:8]}"
    newsroom = await markets.seed_markets(db_session, actor=ACTOR, slug=slug)
    ackman = next(s for s in newsroom.sources if "艾克曼" in s.name)
    assert "CIK=0002026053" in ackman.url and ackman.config["predecessor_ciks"] == ["1336528"]
    ackman.url = markets.edgar_13f("0001336528")  # as seeded before the move
    await db_session.flush()

    again = await markets.seed_markets(db_session, actor=ACTOR, slug=slug)
    assert again.added == [] and "CIK=0002026053" in ackman.url


async def test_the_holdings_dashboard_follows_thirteen_13f_filers(db_session):
    """HD-01: NVIDIA (the company's own investments), Temasek and Soros join the six investors;
    the holdings refresh finds each by the CIK in its feed, as it does the others."""
    slug = f"markets-{uuid.uuid4().hex[:8]}"
    newsroom = await markets.seed_markets(db_session, actor=ACTOR, slug=slug)
    found = holdings.thirteenf_sources(newsroom.sources)
    filers = {holdings.investor_name(source): cik for source, cik in found}
    assert filers == {
        "巴菲特": "1067983",
        "比爾・艾克曼": "2026053",
        "麥可・貝瑞": "1649339",
        "杜肯米勒": "1536411",
        "段永平": "1759760",
        "木頭姐": "1697748",
        "輝達": "1045810",
        "淡馬錫": "1021944",
        "索羅斯": "1029160",
        "橋水": "1350694",
        "蓋茲基金會": "1166559",
        "高瓴": "1762304",
        "沙烏地公共投資基金": "1767640",
    }
    nvidia = next(s for s in newsroom.sources if s.name == "SEC 13F：輝達")
    assert nvidia.config["title_prefix"] == "輝達（NVIDIA）" and nvidia.config["own_story"] is True


def test_searches_stay_inside_the_free_plan():
    """D-253: nine searches — the four kept (台股 AI 伺服器, 台積電, 美股 twice a day; crypto once)
    and the focus's five, twice a day: 510 of Tavily's 1,000 free credits a month (780 before)."""
    searches = [s for s in markets.SOURCES if s.kind == "search_query"]
    assert len(searches) == 9
    monthly = sum(30 * 24 * 3600 // s.poll_interval_seconds for s in searches)
    assert monthly == 510


def test_the_focus_has_its_sources_and_crypto_one_search_a_day():
    """D-253: NVIDIA, TSMC and the AI supply chain; crypto only for the rare big story."""
    names = {s.name for s in markets.SOURCES}
    for name in (
        "NVIDIA Blog",
        "NVIDIA Newsroom",
        "搜尋：輝達",
        "搜尋：台積電：製程與產能",
        "搜尋：AI 伺服器供應鏈",
        "搜尋：HBM 記憶體",
        "搜尋：AI 資料中心：電力與散熱",
    ):
        assert name in names
    crypto = [s for s in markets.SOURCES if s.config.get("section") == "crypto"]
    assert [(s.kind, s.poll_interval_seconds) for s in crypto] == [("search_query", 24 * 3600)]
    assert (
        "2330" in next(s for s in markets.SOURCES if s.kind == "twse_announcements").config["codes"]
    ), "TSMC's own announcements, as its newsroom refuses programs"


def test_what_d253_stopped_covering_is_no_source_of_the_code_s():
    names = {s.name for s in markets.SOURCES}
    stopped = set(markets.RETIRED[2:])
    assert "CoinDesk" in stopped and "搜尋：黃金" in stopped and len(stopped) == 14
    assert not names & stopped


async def test_seeding_pauses_what_d253_stopped_and_sets_the_mix_once(db_session):
    slug = f"focus-{uuid.uuid4().hex[:8]}"
    company = (await markets.seed_markets(db_session, actor=ACTOR, slug=slug)).company
    old = await add_source(
        db_session, company_id=company.id, name="CoinDesk", kind="rss",
        url="https://www.coindesk.com/arc/outboundfeeds/rss/", config={"section": "crypto"},
    )  # fmt: skip
    policies = await get_policies(db_session, company.id)
    assert policies[TOPIC_MIX_KEY] == markets.TOPIC_MIX
    mine = {"focus_terms": ["NVIDIA"], "crypto": 0.0, "other": 0.2}
    await upsert_policy(db_session, company.id, TOPIC_MIX_KEY, mine, updated_by=ACTOR.as_json())

    await markets.seed_markets(db_session, actor=ACTOR, slug=slug)
    await db_session.refresh(old)
    assert old.status == "paused", "its items stay; it is polled no more"
    assert (await get_policies(db_session, company.id))[TOPIC_MIX_KEY] == mine, "the company's"


def test_every_source_says_which_section_of_the_site_it_feeds():
    """D-047: the site's sections come from the sources; one without would feed only the front.
    Since D-253 gold, commodities, FX and institutions' views have no news search: their pages
    are prices and data, refreshed by their own schedules."""
    covered = {s.config["section"] for s in markets.SOURCES}
    assert covered == set(SECTIONS) - {"gold", "commodities", "fx", "institutions"}


async def test_a_section_the_site_does_not_have_is_refused(db_session):
    company = (await markets.seed_markets(db_session, actor=ACTOR, slug="sect-check")).company
    try:
        await add_source(
            db_session,
            company_id=company.id,
            name="nft",
            kind="rss",
            url="https://example.test/feed",
            config={"section": "nft"},
        )
    except SourceConfigError as error:
        assert "config.section" in str(error)
    else:
        raise AssertionError("an unknown section was accepted")


def _migration_0083():
    import importlib.util
    from pathlib import Path

    path = Path(markets.__file__).parents[2] / "db/migrations/versions/0083_ai_focus.py"
    spec = importlib.util.spec_from_file_location("m0083", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_0083_says_what_the_code_says_today():
    """0083 brings D-253 to production as seeding would; its values are written out, and are
    the code's: the mission, the mix, the six added sources, the fourteen paused."""
    m = _migration_0083()
    assert m.MISSION == markets.MISSION
    assert m.TOPIC_MIX == markets.TOPIC_MIX
    assert m.PAUSED == list(markets.RETIRED[2:])
    ours = {s.name: s for s in markets.SOURCES}
    for name, spec in m.ADDED.items():
        source = ours[name]
        assert (source.kind, source.url, str(source.trust_level), source.language) == (
            spec["kind"], spec["url"], spec["trust_level"], spec["language"],
        )  # fmt: skip
        assert source.poll_interval_seconds == spec["poll_interval_seconds"]
        assert source.config == spec["config"]
    assert ours[m.CRYPTO_SEARCH].poll_interval_seconds == 24 * 3600
