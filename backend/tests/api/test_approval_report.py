"""AD-12: how the approvals have gone — decided how, how long it took (median, P90), what ran out
and was asked again, by kind and by who decided, and what has waited too long now."""

import uuid
from datetime import UTC, datetime, timedelta

from autora.db.models import Approval
from tests.conftest import unique_company

REPORT = "/api/approvals/report"
NOW = datetime.now(UTC)
OPERATOR = {"kind": "human", "id": "operator"}
CEO = {"kind": "agent", "id": str(uuid.uuid4())}


def _approval(
    company, *, kind="article", state="PENDING", ago, took=None, by=OPERATOR, summary="x"
):
    created = NOW - ago
    decided = state in ("APPROVED", "REJECTED", "RETURNED")
    return Approval(
        company_id=company.id,
        kind=kind,
        ref_type="test",
        ref_id=uuid.uuid4(),
        summary=summary,
        requested_by={"kind": "system", "id": "t"},
        state=state,
        created_at=created,
        updated_at=created + (took or timedelta(0)),
        decided_at=created + took if decided else None,
        decided_by=by if decided else None,
    )


async def test_the_report(api, db_session):
    company = await unique_company(db_session, "report")
    h = timedelta(hours=1)
    db_session.add_all(
        [
            # articles: 3 approved (1, 2, 10 hours), 1 sent back (4 hours), 1 ran out
            _approval(company, state="APPROVED", ago=20 * h, took=1 * h),
            _approval(company, state="APPROVED", ago=20 * h, took=2 * h),
            _approval(company, state="APPROVED", ago=20 * h, took=10 * h, by=CEO),
            _approval(company, state="RETURNED", ago=20 * h, took=4 * h),
            _approval(company, state="EXPIRED", ago=50 * h, took=24 * h),
            # a command, rejected after half an hour
            _approval(company, kind="command", state="REJECTED", ago=5 * h, took=h / 2),
            # long ago: outside the 30 days
            _approval(company, state="APPROVED", ago=24 * 40 * h, took=h),
            # waiting: one for 2 days (stuck at 24 h), one for an hour (not)
            _approval(company, ago=48 * h, summary="核准發布：等了兩天"),
            _approval(company, kind="command", ago=h, summary="暫停專案"),
        ]
    )
    await db_session.flush()

    report = (await api.get(REPORT, params={"company_id": str(company.id)})).json()
    total = report["total"]
    assert (
        total["decided"],
        total["approved"],
        total["returned"],
        total["rejected"],
        total["expired"],
    ) == (5, 3, 1, 1, 1)
    # decision hours 0.5, 1, 2, 4, 10: median 2; P90 = 4 + 0.6 × (10 − 4) = 7.6
    assert (total["median_hours"], total["p90_hours"]) == (2.0, 7.6)

    articles, command = report["kinds"]
    assert (articles["kind"], articles["decided"], articles["approved"], articles["expired"]) == (
        "article",
        4,
        3,
        1,
    )
    assert (command["kind"], command["rejected"], command["median_hours"]) == ("command", 1, 0.5)

    by = {d["label"]: d for d in report["deciders"]}
    assert (by["操作者權杖"]["decided"], by["操作者權杖"]["returned"]) == (4, 1)
    assert by[CEO["id"]]["approved"] == 1  # an agent no longer in the company: by id

    assert (report["pending"], report["stuck_total"], report["stuck_hours"]) == (2, 1, 24)
    [stuck] = report["stuck"]
    assert (stuck["summary"], round(stuck["waited_hours"])) == ("核准發布：等了兩天", 48)

    # a shorter window and a lower bar
    narrow = (
        await api.get(REPORT, params={"company_id": str(company.id), "days": 1, "stuck_hours": 1})
    ).json()
    assert (
        narrow["total"]["decided"] == 5 and narrow["total"]["expired"] == 0
    )  # it ran out 26 h ago
    assert narrow["stuck_total"] == 2


async def test_nothing_yet_and_who_may_read(api, db_session):
    company = await unique_company(db_session, "report-empty")
    empty = (await api.get(REPORT, params={"company_id": str(company.id)})).json()
    assert empty["total"]["decided"] == 0 and empty["total"]["median_hours"] is None
    assert empty["kinds"] == [] and empty["deciders"] == [] and empty["stuck"] == []
    assert (
        await api.get(REPORT, params={"company_id": str(company.id), "days": 0})
    ).status_code == 422
    assert (
        await api.get(REPORT, params={"company_id": str(company.id)}, headers={"Authorization": ""})
    ).status_code == 401
