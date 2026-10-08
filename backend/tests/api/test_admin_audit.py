"""AD-06: who did what in the back office — every change through its door is written down,
refused ones too, with the route, its target, its company and what was sent (secrets masked);
nothing a person reads is; the record cannot be edited; and no write route slips past the door
unnoticed."""

import uuid

import pytest
from fastapi.routing import APIRoute
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from autora.db.models import AdminAction
from autora_api.app import create_app
from autora_api.audit import _input, _masked
from autora_api.deps import require_operator
from tests.api.test_approvals_api import waiting  # noqa: F401 (fixture)

AUDIT = "/api/admin/audit"

# Writes that do not come through the back office's door, each for a reason: a reader's own
# account and watchlist, the public site, PAYUNi's notification, and the door itself.
PUBLIC_WRITES = {
    ("POST", "/api/analytics/beacon"),
    ("POST", "/api/auth/register"),
    ("POST", "/api/auth/login"),
    ("POST", "/api/auth/logout"),
    ("POST", "/api/auth/email/verify"),
    ("POST", "/api/auth/email/resend"),
    ("POST", "/api/auth/password/forgot"),
    ("POST", "/api/auth/password/reset"),
    ("POST", "/api/admin/auth/login"),
    ("POST", "/api/admin/auth/logout"),
    ("POST", "/api/public/contact"),
    ("POST", "/api/checkout"),
    ("POST", "/api/payments/payuni/notify"),
    ("PUT", "/api/me/watchlist"),
    ("POST", "/api/me/watchlist/{symbol}"),
    ("DELETE", "/api/me/watchlist/{symbol}"),
    ("POST", "/api/me/unlocks/{article_id}"),  # a reader spends their own coins (P4, D-249)
}


def _routes(routes):
    for route in routes:
        if isinstance(route, APIRoute):
            yield route
        elif hasattr(route, "original_router"):  # an included router (FastAPI ≥ 0.140)
            yield from _routes(route.original_router.routes)


def _behind_the_door(dependant) -> bool:
    return dependant.call is require_operator or any(
        _behind_the_door(d) for d in dependant.dependencies
    )


def test_every_write_route_goes_through_the_door_or_is_named_here():
    """A new route that changes something is either the back office's — and so recorded — or a
    deliberate public one added to PUBLIC_WRITES with its reason."""
    writes = {
        (method, route.path, _behind_the_door(route.dependant))
        for route in _routes(create_app().router.routes)
        for method in route.methods - {"GET", "HEAD", "OPTIONS"}
    }
    outside = {(m, p) for m, p, inside in writes if not inside}
    assert outside == PUBLIC_WRITES
    inside = {(m, p) for m, p, behind in writes if behind}
    assert {
        ("POST", "/api/approvals/{approval_id}/decide"),
        ("POST", "/api/articles/{article_id}/unpublish"),
        ("POST", "/api/admin/memberships/comps/{grant_id}/revoke"),
        ("POST", "/api/companies/{company_id}/sources"),
    } <= inside


async def _rows(db_session, **where):
    stmt = select(AdminAction).order_by(AdminAction.created_at, AdminAction.id)
    for key, value in where.items():
        stmt = stmt.where(getattr(AdminAction, key) == value)
    return (await db_session.scalars(stmt)).all()


async def test_a_decision_is_written_down_with_its_target_and_company(api, db_session, waiting):  # noqa: F811
    approval = waiting["approval"]
    response = await api.post(
        f"/api/approvals/{approval.id}/decide", json={"decision": "approve", "reason": "看過了"}
    )
    assert response.status_code == 200, response.text
    [row] = await _rows(db_session, target_id=str(approval.id))
    assert row.actor == {"kind": "human", "id": "operator"}
    assert (row.method, row.route, row.action) == (
        "POST",
        "/api/approvals/{approval_id}/decide",
        "decide",
    )
    assert (row.target_type, row.company_id, row.status) == (
        "approval",
        waiting["company"].id,
        200,
    )
    assert row.input == {"body": {"decision": "approve", "reason": "看過了"}}

    # deciding it again is refused, and the refusal is written down too
    again = await api.post(f"/api/approvals/{approval.id}/decide", json={"decision": "reject"})
    assert again.status_code == 409
    rows = await _rows(db_session, target_id=str(approval.id))
    assert [r.status for r in rows] == [200, 409]


async def test_reading_is_not_written_down_and_nobody_unknown_is(api, db_session, waiting):  # noqa: F811
    company = str(waiting["company"].id)
    await api.get("/api/approvals", params={"company_id": company})
    anonymous = await api.post(
        f"/api/approvals/{waiting['approval'].id}/decide",
        json={"decision": "approve"},
        headers={"Authorization": ""},
    )
    assert anonymous.status_code == 401
    assert await _rows(db_session, company_id=waiting["company"].id) == []


async def test_the_newsroom_changes_that_kept_no_actor_now_have_one(api, db_session, newsroom_room):
    """The access, section and new-source routes took the operator without keeping who it was;
    their changes are now recorded against the article or the company."""
    room = newsroom_room
    article_id = await room.publish()
    await api.post(f"/api/articles/{article_id}/access", json={"access": "members"})
    await api.post(f"/api/articles/{article_id}/section", json={"section": "tw"})
    await api.post(
        f"/api/companies/{room.company.id}/sources",
        json={"name": "TWSE", "kind": "rss", "url": "https://x.test/feed"},
    )
    rows = await _rows(db_session, company_id=room.company.id)
    assert [(r.action, r.target_type, r.status) for r in rows] == [
        ("set_article_access", "article", 200),
        ("set_article_section", "article", 200),
        ("create_source", "company", 201),
    ]
    assert rows[0].target_id == str(article_id) and rows[0].input == {"body": {"access": "members"}}


async def test_the_record_cannot_be_changed(api, db_session, waiting):  # noqa: F811
    await api.post(f"/api/approvals/{waiting['approval'].id}/decide", json={"decision": "approve"})
    [row] = await _rows(db_session, target_id=str(waiting["approval"].id))
    for statement in (
        "UPDATE admin_actions SET status = 200 WHERE id = :id",
        "DELETE FROM admin_actions WHERE id = :id",
    ):
        with pytest.raises(DBAPIError, match="append-only"):
            async with db_session.begin_nested():
                await db_session.execute(text(statement), {"id": row.id})


async def test_the_record_is_listed_newest_first_and_filtered(api, db_session, waiting):  # noqa: F811
    approval = waiting["approval"]
    await api.post(f"/api/approvals/{approval.id}/decide", json={"decision": "approve"})
    await api.post(f"/api/approvals/{approval.id}/decide", json={"decision": "reject"})
    company = str(waiting["company"].id)

    page = (await api.get(AUDIT, params={"company_id": company})).json()
    assert page["total"] == 2
    assert [i["status"] for i in page["items"]] == [409, 200]
    assert page["items"][0]["actor_label"] == "操作者權杖"
    assert (await api.get(AUDIT, params={"company_id": company, "failed": True})).json()[
        "total"
    ] == 1
    assert (await api.get(AUDIT, params={"company_id": company, "q": "DECIDE"})).json()[
        "total"
    ] == 2
    assert (
        await api.get(AUDIT, params={"company_id": company, "target_id": str(uuid.uuid4())})
    ).json()["total"] == 0
    assert (await api.get(AUDIT, headers={"Authorization": ""})).status_code == 401


def test_what_was_sent_is_kept_without_secrets_and_without_bulk():
    assert _masked(
        {"password": "x", "nested": {"api_token": "y", "ok": 1}, "list": [{"secret": 2}]}
    ) == {
        "password": "***",
        "nested": {"api_token": "***", "ok": 1},
        "list": [{"secret": "***"}],
    }
    long = _masked({"text": "字" * 3000})["text"]
    assert long.startswith("字" * 2000) and long.endswith("（共 3000 字）")

    scope = {"query_string": b"company=aisiwhale&token=abc"}
    assert _input(scope, b'{"reason": "x"}', False) == {
        "query": {"company": "aisiwhale", "token": "***"},
        "body": {"reason": "x"},
    }
    assert _input(scope, b"\x89PNG", False)["body"] == "（4 位元組，不是 JSON）"
    assert _input({}, b"x" * 10, True) == {"body": "（10 位元組以上，未保存）"}
    big = _input(
        {}, ("{" + ",".join(f'"k{i}": "{"v" * 1500}"' for i in range(20)) + "}").encode(), False
    )
    assert big["truncated"] is True and big["body_keys"][:2] == ["k0", "k1"]
