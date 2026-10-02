"""D-169: the TWSE material announcements and GDELT, read like feeds and polled like them."""

import asyncio
import json
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from autora.domains.newsroom.datafeeds import (
    TWSE_URL,
    GdeltBusy,
    gdelt_url,
    parse_gdelt,
    parse_twse_announcements,
)
from autora.domains.newsroom.feeds import FeedError
from autora.domains.newsroom.models import SourceItem
from autora.domains.newsroom.sources import SourceConfigError, add_source
from autora.infra.http import FetchedPage
from tests.conftest import unique_company
from tests.newsroom.test_sources import FIXTURES, T0, poller

TWSE = (FIXTURES / "feeds" / "twse-announcements.json").read_bytes()
GDELT = (FIXTURES / "feeds" / "gdelt-artlist.json").read_bytes()


def test_an_announcement_in_the_roc_calendar_and_its_own_url():
    first, *_ = parse_twse_announcements(TWSE)
    # 1151001 and 5311 are 2026-10-01 00:53:11 in Taipei
    assert first.published_at == datetime(2026, 9, 30, 16, 53, 11, tzinfo=UTC)
    assert first.title == "弘凱（5244）公告本公司新任技術長"  # "主旨 " has a stray space
    assert first.url.startswith(f"{TWSE_URL}?co_id=5244&at=20260930T165311Z&id=")
    assert "新任者姓名及簡歷：王大同" in first.summary
    assert "符合條款：第8款" in first.summary and "事實發生日：2026-10-01" in first.summary
    assert len({e.url for e in parse_twse_announcements(TWSE)}) == 3
    row = {"公司代號": "2882", "公司名稱": "國泰金", "主旨": "代子公司公告董事會決議，\n贖回債券"}
    broken = json.dumps([row]).encode()
    [one] = parse_twse_announcements(broken)
    assert one.title == "國泰金（2882）代子公司公告董事會決議，贖回債券"


def test_announcements_only_of_some_companies_or_some_subjects():
    assert [e.title.split("（")[0] for e in parse_twse_announcements(TWSE, codes=["2330"])] == [
        "台積電"
    ]
    picked = parse_twse_announcements(TWSE, codes=["2330"], keywords=["公司債"])
    assert [e.title.split("（")[0] for e in picked] == ["台積電", "台泥"]


def test_gdelt_articles_and_its_answers_that_are_not_news():
    first, second = parse_gdelt(GDELT)  # the one without a link is dropped
    assert first.title == "TSMC starts 2nm volume production in Kaohsiung"
    assert first.published_at == datetime(2026, 10, 2, 8, 15, tzinfo=UTC)
    assert second.summary == "example-tw.test"
    assert parse_gdelt(b"") == []  # nothing matched
    with pytest.raises(GdeltBusy):
        parse_gdelt(b"Please limit requests to one every 5 seconds")
    with pytest.raises(FeedError, match="did not answer JSON"):
        parse_gdelt(b"<html>Service Unavailable</html>")
    url = gdelt_url({"query": '"TSMC" sourcelang:english', "timespan": "6h"})
    assert "mode=artlist" in url and "timespan=6h" in url and "maxrecords=25" in url


@pytest.mark.parametrize(
    ("kind", "config"),
    [
        ("twse_announcements", {"codes": "2330"}),
        ("twse_announcements", {"codes": ["2330; DROP"]}),
        ("twse_announcements", {"keywords": [""]}),
        ("gdelt", {}),
        ("gdelt", {"query": "x", "maxrecords": 0}),
        ("gdelt", {"query": "x", "timespan": "yesterday"}),
    ],
)
async def test_a_wrong_config_is_refused(db_session, kind, config):
    company = await unique_company(db_session, "datafeed-bad")
    with pytest.raises(SourceConfigError):
        await add_source(db_session, company_id=company.id, name="x", kind=kind, config=config)


async def test_both_are_polled_into_items(db_session):
    company = await unique_company(db_session, "datafeeds")
    twse = await add_source(
        db_session,
        company_id=company.id,
        name="證交所重大訊息",
        kind="twse_announcements",
        config={"codes": ["2330", "5244"], "section": "tw", "primary": True},
        now=T0,
    )
    gdelt = await add_source(
        db_session,
        company_id=company.id,
        name="GDELT：台積電",
        kind="gdelt",
        config={"query": "TSMC"},
        now=T0,
    )
    both = poller()
    assert len((await both.poll(db_session, twse)).new_item_ids) == 2
    assert len((await both.poll(db_session, gdelt)).new_item_ids) == 2
    items = (
        await db_session.scalars(select(SourceItem).where(SourceItem.company_id == company.id))
    ).all()
    urls = {i.url for i in items}
    assert "https://www.example-news.test/tsmc-2nm" in urls  # tracking removed
    kept = next(i for i in items if i.title.startswith("台積電"))
    assert "交易總金額：新台幣120億元" in kept.summary
    # polled again: nothing new
    assert (await both.poll(db_session, twse)).new_item_ids == []


async def test_gdelt_is_asked_once_every_few_seconds(db_session):
    company = await unique_company(db_session, "gdelt-gap")
    sources = [
        await add_source(
            db_session,
            company_id=company.id,
            name=f"GDELT {n}",
            kind="gdelt",
            config={"query": f"q{n}"},
            now=T0,
        )
        for n in range(3)
    ]
    asked: list[float] = []

    class Timed:
        async def fetch(self, url):
            asked.append(asyncio.get_running_loop().time())
            return FetchedPage(url=url, status=200, content_type="application/json", body=GDELT)

    outcomes = await poller(fetcher=Timed(), gdelt_gap_seconds=0.2)._poll(db_session, sources)
    assert all(o.error is None for o in outcomes)
    gaps = [b - a for a, b in zip(asked, asked[1:], strict=False)]
    assert len(asked) == 3 and all(g >= 0.19 for g in gaps)


def test_gdelt_titles_lose_their_stray_spaces():
    body = b'{"articles": [{"url": "https://x.test/a", "title": "The Real Prize  Is Here . ", '
    body += b'"seendate": "20261001T201500Z"}]}'
    [entry] = parse_gdelt(body)
    assert entry.title == "The Real Prize Is Here."


async def test_gdelt_asking_to_slow_down_does_not_pause_the_source(db_session):
    company = await unique_company(db_session, "gdelt-busy")
    source = await add_source(
        db_session, company_id=company.id, name="GDELT", kind="gdelt", config={"query": "q"}
    )

    class Busy:
        async def fetch(self, url):
            body = b"Please limit requests to one every 5 seconds or contact ..."
            return FetchedPage(url=url, status=200, content_type="text/html", body=body)

    busy = poller(fetcher=Busy(), gdelt_gap_seconds=0)
    for _ in range(busy.pause_after + 1):
        outcome = await busy.poll(db_session, source)
    assert outcome.error.startswith("GdeltBusy") and not outcome.paused
    assert source.consecutive_failures == 0 and source.status == "active"
