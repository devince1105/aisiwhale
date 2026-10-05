"""D-047: the public site in sections, a page at a time, with the next article along."""

import uuid
from datetime import timedelta

import httpx
import pytest

from autora.domains.newsroom.models import (
    Article,
    ArticleVersion,
    Source,
    SourceItem,
    Story,
    StoryItem,
)
from autora.domains.newsroom.sources import SECTION, SECTIONS
from autora_api.routers.public import Section


@pytest.fixture
async def public(api):
    async with httpx.AsyncClient(transport=api._transport, base_url="http://test") as client:
        yield client


async def _from_sources(session, company_id, story_id, sections):
    """Give the story one item from a source for each section named (None: a source without)."""
    for n, section in enumerate(sections):
        source = Source(
            company_id=company_id,
            name=f"src-{uuid.uuid4().hex[:8]}",
            kind="rss",
            url="https://example.test/feed.xml",
            config={SECTION: section} if section else {},
        )
        session.add(source)
        await session.flush()
        item = SourceItem(
            company_id=company_id,
            source_id=source.id,
            external_id=f"x{n}",
            url=f"https://example.test/{uuid.uuid4().hex}",
            title="t",
            content_hash=uuid.uuid4().hex,
        )
        session.add(item)
        await session.flush()
        session.add(StoryItem(story_id=story_id, source_item_id=item.id, company_id=company_id))


async def _another(session, first: Article, *, later: timedelta) -> Article:
    """A second article on the site, published ``later`` than the first (a copy of its text)."""
    story = Story(company_id=first.company_id, title="another", state="PUBLISHED")
    session.add(story)
    await session.flush()
    group = uuid.uuid4()
    article = Article(
        company_id=first.company_id,
        story_id=story.id,
        slug=f"another-{uuid.uuid4().hex[:6]}",
        title="another",
        state="PUBLISHED",
        primary_lang="zh-TW",
        published_langs=["zh-TW"],
        published_at=first.published_at + later,
        published_group_id=group,
    )
    session.add(article)
    await session.flush()
    session.add(
        ArticleVersion(
            company_id=first.company_id,
            article_id=article.id,
            version=1,
            lang="zh-TW",
            draft_group_id=group,
            title=f"另一篇 {later}",
            summary=None,
            body=[{"type": "paragraph", "text": "x", "claim_ids": []}],
            claim_ids=[],
        )
    )
    return article


def test_the_api_spells_out_the_same_sections():
    assert Section.__args__ == SECTIONS


async def test_an_article_is_in_the_section_most_of_its_sources_name(public, newsroom_room):
    room = newsroom_room
    await room.publish()
    list_ = {"lang": "zh-TW", "company": room.company.slug}
    only = (await public.get("/api/public/articles", params=list_)).json()
    assert [a["section"] for a in only] == [None]  # no source says: front page only
    assert (await public.get("/api/public/articles", params=list_ | {"section": "ai"})).json() == []

    async with room.committed() as session:
        await _from_sources(session, room.company.id, room.story.id, ["ai", "tw", "ai", None])
        await session.commit()
    ai = (await public.get("/api/public/articles", params=list_ | {"section": "ai"})).json()
    assert [a["section"] for a in ai] == ["ai"]
    assert (await public.get("/api/public/articles", params=list_ | {"section": "tw"})).json() == []
    one = await public.get(f"/api/public/articles/zh-TW/{ai[0]['slug']}")
    assert one.json()["section"] == "ai"
    # several sections: any of them (the site's 持股觀察 is two, D-050)
    both = await public.get("/api/public/articles", params=list_ | {"section": ["tw", "ai"]})
    assert [a["section"] for a in both.json()] == ["ai"]
    neither = await public.get("/api/public/articles", params=list_ | {"section": ["tw", "us"]})
    assert neither.json() == []
    bad = await public.get("/api/public/articles", params=list_ | {"section": "nft"})
    assert bad.status_code == 422


async def test_a_section_a_person_gives_wins_and_can_be_taken_back(api, public, newsroom_room):
    """D-208: 10/05's brief about the TAIEX had no sources, so it was on the front page only."""
    room = newsroom_room
    article_id = await room.publish()
    list_ = {"lang": "zh-TW", "company": room.company.slug}

    given = await api.post(f"/api/articles/{article_id}/section", json={"section": "tw"})
    assert given.status_code == 200, given.text
    assert given.json()["section"] == "tw"
    tw = (await public.get("/api/public/articles", params=list_ | {"section": "tw"})).json()
    assert [a["section"] for a in tw] == ["tw"]
    detail = (await api.get(f"/api/articles/{article_id}")).json()
    assert (detail["section"], detail["section_given"]) == ("tw", True)

    async with room.committed() as session:
        await _from_sources(session, room.company.id, room.story.id, ["ai", "ai"])
        await session.commit()
    one = await public.get(f"/api/public/articles/zh-TW/{tw[0]['slug']}")
    assert one.json()["section"] == "tw"  # the person's choice, over what the sources say

    back = await api.post(f"/api/articles/{article_id}/section", json={"section": None})
    assert back.json()["section"] == "ai"  # automatic again: the sources decide
    detail = (await api.get(f"/api/articles/{article_id}")).json()
    assert (detail["section"], detail["section_given"]) == ("ai", False)

    bad = await api.post(f"/api/articles/{article_id}/section", json={"section": "nft"})
    assert bad.status_code == 422
    missing = await api.post(f"/api/articles/{uuid.uuid4()}/section", json={"section": "tw"})
    assert missing.status_code == 404


async def test_a_story_s_own_words_count_last(api, public, newsroom_room):
    """D-212: the words of a brief place it — but its sources, when it gathers some, come first,
    and a person's choice before both."""
    room = newsroom_room
    article_id = await room.publish()
    async with room.committed() as session:
        story = await session.get(Story, room.story.id)
        story.seed = {"query": "台股收盤", "section_guess": "tw"}
        await session.commit()
    detail = (await api.get(f"/api/articles/{article_id}")).json()
    assert (detail["section"], detail["section_given"]) == ("tw", False)

    async with room.committed() as session:
        await _from_sources(session, room.company.id, room.story.id, ["ai"])
        await session.commit()
    assert (await api.get(f"/api/articles/{article_id}")).json()["section"] == "ai"

    await api.post(f"/api/articles/{article_id}/section", json={"section": "us"})
    assert (await api.get(f"/api/articles/{article_id}")).json()["section"] == "us"


async def test_pages_and_the_next_article_along(public, newsroom_room):
    room = newsroom_room
    first_id = uuid.UUID(await room.publish())
    async with room.committed() as session:
        first = await session.get(Article, first_id)
        newer = await _another(session, first, later=timedelta(hours=1))
        older = await _another(session, first, later=-timedelta(hours=1))
        await session.commit()
        slugs = [newer.slug, first.slug, older.slug]

    list_ = {"lang": "zh-TW", "company": room.company.slug, "limit": 2}
    first_page = await public.get("/api/public/articles", params=list_)
    page1 = first_page.json()
    page2 = (await public.get("/api/public/articles", params=list_ | {"offset": 2})).json()
    assert [a["slug"] for a in page1 + page2] == slugs
    # how many in all, for the list's page numbers (D-065): every page says the same
    assert first_page.headers["X-Total-Count"] == "3"
    ai_only = await public.get("/api/public/articles", params=list_ | {"section": "ai"})
    assert ai_only.headers["X-Total-Count"] == "0"

    middle = (await public.get(f"/api/public/articles/zh-TW/{first.slug}")).json()
    assert middle["newer"] == {
        "title": "另一篇 1:00:00",
        "path": f"/news/zh-TW/articles/{newer.slug}",
    }
    assert middle["older"]["path"] == f"/news/zh-TW/articles/{older.slug}"
    top = (await public.get(f"/api/public/articles/zh-TW/{newer.slug}")).json()
    assert top["newer"] is None and top["older"]["path"] == f"/news/zh-TW/articles/{first.slug}"


async def test_a_day_s_stories_and_a_month_s_calendar_in_taipei(public, newsroom_room):
    """D-084: a reader pages back by date. A story at 23:30 in Taipei (15:30 UTC) is that day's;
    the calendar says which days of a month have stories, and how many."""
    from datetime import UTC, datetime

    room = newsroom_room
    first_id = uuid.UUID(await room.publish())
    async with room.committed() as session:
        first = await session.get(Article, first_id)
        first.published_at = datetime(2026, 9, 24, 15, 30, tzinfo=UTC)  # 9/24 23:30 in Taipei
        same_day = await _another(session, first, later=-timedelta(hours=10))  # 9/24 13:30
        next_day = await _another(session, first, later=timedelta(hours=1))  # 9/25 00:30
        await _another(session, first, later=-timedelta(days=30))  # August
        await session.commit()
        slugs = (first.slug, same_day.slug, next_day.slug)

    list_ = {"lang": "zh-TW", "company": room.company.slug}
    day = await public.get("/api/public/articles", params=list_ | {"day": "2026-09-24"})
    assert {a["slug"] for a in day.json()} == {slugs[0], slugs[1]}
    assert day.headers["X-Total-Count"] == "2"
    after = (await public.get("/api/public/articles", params=list_ | {"day": "2026-09-25"})).json()
    assert [a["slug"] for a in after] == [slugs[2]]

    month = await public.get("/api/public/articles/calendar", params=list_ | {"month": "2026-09"})
    assert month.json() == [{"day": "2026-09-24", "count": 2}, {"day": "2026-09-25", "count": 1}]
    august = (
        await public.get("/api/public/articles/calendar", params=list_ | {"month": "2026-08"})
    ).json()
    assert [d["count"] for d in august] == [1]
    none = await public.get(
        "/api/public/articles/calendar", params=list_ | {"month": "2026-09", "section": "ai"}
    )
    assert none.json() == []
    assert (
        await public.get("/api/public/articles/calendar", params=list_ | {"month": "2026-13"})
    ).status_code == 422


async def test_the_most_read_of_the_last_week(public, newsroom_room):
    """D-086: 熱門文章 — the week's opened pages, most first, the newer on a tie; older reads and
    another language's do not count."""
    from datetime import UTC, datetime

    from autora.domains.newsroom.models import AnalyticsEvent

    room = newsroom_room
    list_ = {"lang": "zh-TW", "company": room.company.slug}
    assert (await public.get("/api/public/articles/popular", params=list_)).json() == []
    first_id = uuid.UUID(await room.publish())
    async with room.committed() as session:
        first = await session.get(Article, first_id)
        newer = await _another(session, first, later=timedelta(hours=1))
        older = await _another(session, first, later=-timedelta(hours=1))
        now = datetime.now(UTC)

        def read(article, n, *, ago=timedelta(0), lang="zh-TW"):
            for _ in range(n):
                session.add(
                    AnalyticsEvent(
                        company_id=article.company_id,
                        article_id=article.id,
                        lang=lang,
                        event_type="view",
                        session_hash=f"{uuid.uuid4().hex}",
                        day=(now - ago).date(),
                        created_at=now - ago,
                    )  # fmt: skip
                )

        read(first, 3)
        read(newer, 1)
        read(older, 1)
        read(older, 9, ago=timedelta(days=10))  # last month's hit
        read(newer, 9, lang="en")  # another language's reads
        await session.commit()
        expected = [first.slug, newer.slug, older.slug]

    popular = (await public.get("/api/public/articles/popular", params=list_)).json()
    assert [a["slug"] for a in popular] == expected  # 3 reads, then a tie: the newer first
    two = (await public.get("/api/public/articles/popular", params=list_ | {"limit": 2})).json()
    assert len(two) == 2
