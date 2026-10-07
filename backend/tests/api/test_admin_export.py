"""AD-13: a back-office list as CSV — every page of it under the same filters and order, the
table's headers, Excel's byte-order mark, no formula smuggled in from a feed, and the export
itself in the audit trail with how many rows left."""

import csv
import io
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from autora.domains.newsroom.models import Story
from autora_api import permissions
from autora_api.export import cell
from tests.api.test_membership_p2_api import _grant, _tester, shop  # noqa: F401 - the fixture
from tests.conftest import unique_company


def _csv(response):
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/csv")
    assert response.content.startswith(b"\xef\xbb\xbf")  # Excel reads it as UTF-8
    return list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"))))


async def test_every_page_under_the_same_filters_and_order(api, db_session):
    company = await unique_company(db_session, "export")
    now = datetime.now(UTC)
    db_session.add_all(
        Story(
            company_id=company.id,
            title=f"題材 {n:03}",
            state="SELECTED" if n % 2 else "DISCOVERED",
            score=Decimal(n) / 1000,
            first_seen_at=now - timedelta(minutes=n),
        )
        for n in range(250)
    )
    db_session.add(Story(company_id=company.id, title='=HYPERLINK("x")', state="SELECTED"))
    await db_session.flush()
    url = f"/api/companies/{company.id}/stories"

    response = await api.get(f"{url}/export", params={"state": "SELECTED", "sort": "-score"})
    rows = _csv(response)
    assert rows[0][:3] == ["狀態", "題材", "分數"]
    body = rows[1:]
    # 125 odd ones and the formula: more than one page of 100, none lost, the list's order
    assert len(body) == 126 and response.headers["x-export-rows"] == "126"
    assert response.headers["x-export-total"] == "126"
    assert {r[0] for r in body} == {"SELECTED"}
    assert [r[1] for r in body[:2]] == ["題材 249", "題材 247"]
    assert '\'=HYPERLINK("x")' in [r[1] for r in body]
    assert "attachment" in response.headers["content-disposition"]

    searched = _csv(await api.get(f"{url}/export", params={"q": "題材 24"}))
    # every word somewhere in the title, as the list searches
    expected = sorted(f"題材 {n:03}" for n in range(250) if "24" in f"{n:03}")
    assert sorted(r[1] for r in searched[1:]) == expected

    # the export is in the audit trail, with its filters and how many rows left
    trail = (await api.get("/api/admin/audit", params={"company_id": str(company.id)})).json()
    [first, *_] = [a for a in trail["items"] if a["action"] == "export_stories"]
    assert first["method"] == "GET" and first["actor_label"] == "操作者權杖"
    assert first["input"]["rows"] == len(expected) and first["input"]["query"] == {"q": "題材 24"}


async def test_the_other_lists(api, db_session, shop):  # noqa: F811
    company, _ = shop
    await _tester(db_session)
    assert (await _grant(api, company, reason="=1+1")).status_code == 201
    comps = _csv(
        await api.get("/api/admin/memberships/comps/export", params={"company": company.slug})
    )
    assert comps[0][:3] == ["讀者", "有效中", "開始"]
    [comp] = comps[1:]
    assert (comp[0], comp[1], comp[4]) == ("tester@example.com", "是", "'=1+1")

    for path in ("articles", "sources"):
        empty = _csv(await api.get(f"/api/companies/{company.id}/{path}/export"))
        assert len(empty) == 1  # the headers alone

    audit = _csv(await api.get("/api/admin/audit/export", params={"company_id": str(company.id)}))
    assert audit[0][:3] == ["時間", "誰", "方法"]
    actions = [r[4] for r in audit[1:]]
    assert "grant_comp" in actions and "export_comps" in actions  # the grant, and its export


def test_who_may_take_the_audit_trail_and_how_a_cell_reads():
    assert permissions.needed("GET", "/api/admin/audit/export") == permissions.AUDIT
    taipei = datetime(2026, 10, 7, 12, 30, tzinfo=UTC)
    assert cell(taipei) == "2026-10-07 20:30"
    assert (cell(True), cell(None), cell(Decimal("0.75"))) == ("是", "", "0.75")
    assert cell({"題": 1}) == '{"題": 1}'
    for formula in ("=SUM(A1)", "+1", "-1", "@x"):
        assert cell(formula) == f"'{formula}"
