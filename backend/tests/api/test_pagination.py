"""AD-04: the back office's lists, a page at a time — ?cursor=&limit=&q=&sort= →
{items, next_cursor, total} — on the approval inbox (the one that used to return everything),
and the cursor and search rules every list shares."""

import time
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from autora.db.models import Approval
from autora_api.pagination import ListParams, Sort, make_cursor, matches, page_list, read_cursor
from tests.conftest import unique_company

INBOX = "/api/approvals"


async def _approvals(
    session, company, summaries, *, at=None, step=timedelta(0), action="publish_article"
):
    """Pending approvals with these summaries; created at ``at`` + i * ``step`` (the same moment
    when ``step`` is zero, as rows written in one transaction are)."""
    start = at or datetime(2026, 10, 1, tzinfo=UTC)
    rows = [
        Approval(
            company_id=company.id,
            kind="tool_call",
            ref_type="test",
            ref_id=uuid.uuid4(),
            action=action,
            summary=summary,
            requested_by={"kind": "system", "id": "test"},
            created_at=start + i * step,
        )
        for i, summary in enumerate(summaries)
    ]
    session.add_all(rows)
    await session.flush()
    return rows


async def _all_pages(api, params, limit):
    seen, cursor, pages = [], None, 0
    while True:
        query = {**params, "limit": limit, **({"cursor": cursor} if cursor else {})}
        body = (await api.get(INBOX, params=query)).json()
        seen += [item["id"] for item in body["items"]]
        pages += 1
        cursor = body["next_cursor"]
        if cursor is None:
            return seen, pages, body["total"]


async def test_pages_through_the_inbox_in_order_without_a_gap(api, db_session):
    company = await unique_company(db_session, "pages")
    rows = await _approvals(
        db_session, company, [f"item {i}" for i in range(7)], step=timedelta(minutes=1)
    )
    first = (await api.get(INBOX, params={"company_id": str(company.id), "limit": 3})).json()
    assert [i["summary"] for i in first["items"]] == ["item 0", "item 1", "item 2"]
    assert first["total"] == 7 and first["next_cursor"]

    seen, pages, total = await _all_pages(api, {"company_id": str(company.id)}, 3)
    assert seen == [str(r.id) for r in rows] and pages == 3 and total == 7

    newest = (
        await api.get(INBOX, params={"company_id": str(company.id), "sort": "-created_at"})
    ).json()
    assert [i["summary"] for i in newest["items"]][:2] == ["item 6", "item 5"]

    # exactly a page's worth: one page, no cursor to an empty one
    exact = (await api.get(INBOX, params={"company_id": str(company.id), "limit": 7})).json()
    assert len(exact["items"]) == 7 and exact["next_cursor"] is None


async def test_rows_written_at_the_same_moment_are_neither_lost_nor_repeated(api, db_session):
    """Keyset paging on created_at alone would skip or repeat rows that share it; the id breaks
    the tie in the same direction."""
    company = await unique_company(db_session, "ties")
    rows = await _approvals(db_session, company, [f"tie {i}" for i in range(10)])
    for sort in ("created_at", "-created_at"):
        seen, pages, _ = await _all_pages(api, {"company_id": str(company.id), "sort": sort}, 4)
        assert sorted(seen) == sorted(str(r.id) for r in rows) and len(seen) == 10
        assert pages == 3
    asc, _, _ = await _all_pages(api, {"company_id": str(company.id)}, 4)
    desc, _, _ = await _all_pages(api, {"company_id": str(company.id), "sort": "-created_at"}, 4)
    assert asc == list(reversed(desc))


async def test_search_every_word_ignoring_case_and_wildcards(api, db_session):
    company = await unique_company(db_session, "search")
    await _approvals(
        db_session,
        company,
        ["Publish 台股創新高", "publish the Nasdaq note", "Pause project X", "100% sure_thing"],
        step=timedelta(seconds=1),
        action="pause_project",
    )

    async def found(q):
        body = (await api.get(INBOX, params={"company_id": str(company.id), "q": q})).json()
        return [i["summary"] for i in body["items"]], body["total"]

    assert await found("PUBLISH") == (["Publish 台股創新高", "publish the Nasdaq note"], 2)
    assert await found("publish nasdaq") == (["publish the Nasdaq note"], 1)
    assert await found("台股") == (["Publish 台股創新高"], 1)
    assert await found("100%") == (["100% sure_thing"], 1)
    assert await found("%") == (["100% sure_thing"], 1), "% is a character, not a wildcard"
    assert await found("e_t") == (["100% sure_thing"], 1), "_ too"
    assert (await found("pause_project"))[1] == 4, "the action is searched as well"
    assert await found("   ") == (
        ["Publish 台股創新高", "publish the Nasdaq note", "Pause project X", "100% sure_thing"],
        4,
    )


async def test_a_bad_cursor_is_a_problem_not_a_crash(api, db_session):
    company = await unique_company(db_session, "badcursor")
    await _approvals(db_session, company, ["a", "b"], step=timedelta(seconds=1))
    params = {"company_id": str(company.id), "limit": 1}
    cursor = (await api.get(INBOX, params=params)).json()["next_cursor"]

    for bad in ("not-a-cursor", "eyJ4IjoxfQ", cursor[:-3]):
        response = await api.get(INBOX, params={**params, "cursor": bad})
        assert response.status_code == 400, bad
        assert response.headers["content-type"].startswith("application/problem+json")

    other = await api.get(INBOX, params={**params, "cursor": cursor, "sort": "-created_at"})
    assert other.status_code == 400 and "another sort" in other.json()["detail"]

    for bad_query in ({"limit": 0}, {"limit": 101}, {"sort": "summary"}):
        assert (await api.get(INBOX, params={**params, **bad_query})).status_code == 422


@pytest.mark.parametrize(
    "path, sort",
    [
        ("/api/companies/{id}/stories", "-score"),
        ("/api/companies/{id}/articles", "title"),
        ("/api/companies/{id}/sources", "name"),
    ],
)
async def test_the_newsroom_lists_take_the_same_parameters(api, newsroom_room, path, sort):
    url = path.format(id=newsroom_room.company.id)
    body = (await api.get(url, params={"limit": 1, "sort": sort, "q": "zz-nothing"})).json()
    assert body == {"items": [], "next_cursor": None, "total": 0}
    assert (await api.get(url, params={"sort": "nope"})).status_code == 422


async def test_a_thousand_pending_answer_a_page_quickly(api, db_session):
    """The inbox used to return every row; a page of a thousand is one index range."""
    company = await unique_company(db_session, "thousand")
    await _approvals(
        db_session, company, [f"bulk {i}" for i in range(1000)], step=timedelta(seconds=1)
    )
    params = {"company_id": str(company.id)}
    await api.get(INBOX, params=params)  # warm the connection and the plan
    # the best of three: one slow sample on a busy machine (a full run beside other work, CI)
    # says nothing about the query
    timings = []
    for _ in range(3):
        started = time.perf_counter()
        first = (await api.get(INBOX, params=params)).json()
        deep = (await api.get(INBOX, params={**params, "cursor": first["next_cursor"]})).json()
        timings.append((time.perf_counter() - started) / 2)
    took = min(timings)
    assert first["total"] == 1000 and len(first["items"]) == 50 and len(deep["items"]) == 50
    assert took < 0.2, f"{took * 1000:.0f} ms a page"


def test_the_cursor_round_trips_and_names_its_sort():
    sort = Sort(param="-created_at", column=Approval.created_at, descending=True)
    at, row = datetime(2026, 10, 7, 12, 30, tzinfo=UTC), uuid.uuid4()
    assert read_cursor(make_cursor(sort, at, row), sort) == (at, row)


def test_a_page_from_rows_in_memory_follows_the_same_rules():
    """The comps list pages a whole list the domain returns (page_list)."""
    base = datetime(2026, 10, 1, tzinfo=UTC)
    rows = [(base + timedelta(minutes=i // 2), uuid.UUID(int=i)) for i in range(5)]  # ties
    sort = Sort(param="-created_at", column=Approval.created_at, descending=True)
    seen, cursor = [], None
    while True:
        page, cursor, total = page_list(
            rows,
            sort=sort,
            value=lambda r: r[0],
            row_id=lambda r: r[1],
            listing=ListParams(cursor=cursor, limit=2, q=None),
        )
        seen += page
        if cursor is None:
            break
    assert seen == sorted(rows, reverse=True) and total == 5
    assert matches(["VIP", "測試"], "vip 內部測試") and not matches(["vip", "付費"], "vip 內部測試")
