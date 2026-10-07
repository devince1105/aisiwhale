"""AD-09: who may do what in the back office. Every write route has a permission key; each of the
four roles is refused (403) exactly the keys it lacks, and may read the rest; ADMIN_EMAILS and the
operator token are owners; owners let others in, as a role, and the record keeps it."""

import uuid

import pytest
from fastapi.routing import APIRoute
from sqlalchemy import select

from autora.accounts import credentials
from autora.accounts.models import Reader
from autora.db.models import AdminAction, AdminRole
from autora_api import permissions
from autora_api.app import create_app
from autora_api.deps import ADMIN_COOKIE, require_operator
from tests.api.conftest import ADMIN
from tests.conftest import unique_company

PASSWORD = "correct horse battery"
ANON = {"Authorization": ""}
ROLES = ("owner", "editor", "finance", "viewer")


def _routes(routes):
    for route in routes:
        if isinstance(route, APIRoute):
            yield route
        elif hasattr(route, "original_router"):
            yield from _routes(route.original_router.routes)


def _behind_the_door(dependant) -> bool:
    return dependant.call is require_operator or any(
        _behind_the_door(d) for d in dependant.dependencies
    )


ALL_ROUTES = [
    (method, route.path, _behind_the_door(route.dependant))
    for route in _routes(create_app().router.routes)
    for method in route.methods - {"HEAD", "OPTIONS"}
]


def test_every_back_office_write_has_a_key_and_every_key_a_route():
    writes = {(m, p) for m, p, inside in ALL_ROUTES if inside and m != "GET"}
    assert writes - set(permissions.ROUTES) == set(), "a write route without a permission key"
    real = {(m, p) for m, p, _ in ALL_ROUTES}
    assert set(permissions.ROUTES) - real == set(), "a key for a route that does not exist"
    assert set(permissions.ROUTES.values()) <= permissions.ALL


def test_the_four_roles():
    assert permissions.permissions_of("owner") == permissions.ALL
    # a viewer changes nothing but its own settings (AD-10)
    assert permissions.permissions_of("viewer") == frozenset({"self:prefs"})
    assert "coins:adjust" in permissions.permissions_of("finance")
    assert "coins:adjust" not in permissions.permissions_of("editor")
    assert "approvals:decide" in permissions.permissions_of("editor")
    assert "access:manage" not in permissions.permissions_of("finance")
    # D-248: a trade is approved by an owner or finance, nobody else
    assert {
        r
        for r in ("owner", "editor", "finance", "viewer")
        if "trading:approve" in permissions.permissions_of(r)
    } == {"owner", "finance"}
    assert permissions.permissions_of("nobody") == frozenset()


async def _signed_in(api, db_session, address: str, role: str | None, *, prove=True) -> uuid.UUID:
    """A reader with ``role`` (None: an ADMIN_EMAILS owner), signed in to the back office."""
    outcome = await credentials.register(db_session, address, PASSWORD)
    if prove:
        await credentials.verify_email(db_session, outcome.verify_token)
    reader = await db_session.scalar(select(Reader).where(Reader.email == address))
    if role is not None:
        db_session.add(
            AdminRole(reader_id=reader.id, role=role, granted_by={"kind": "human", "id": "test"})
        )
    await db_session.flush()
    api.cookies.clear()
    response = await api.post(
        "/api/admin/auth/login", json={"email": address, "password": PASSWORD}, headers=ANON
    )
    assert response.status_code == 200, response.text
    api.cookies.set(ADMIN_COOKIE, response.cookies[ADMIN_COOKIE])
    return reader.id


def _url(path: str, company_id: uuid.UUID) -> str:
    out = path.replace("{company_id}", str(company_id))
    while "{" in out:
        start = out.index("{")
        out = out[:start] + str(uuid.uuid4()) + out[out.index("}") + 1 :]
    return out


@pytest.mark.parametrize("role", ROLES)
async def test_each_role_is_refused_exactly_what_it_may_not_do(api, db_session, role):
    company = await unique_company(db_session, f"perm-{role}")
    await _signed_in(api, db_session, f"{role}@perm.test", role)
    allowed = permissions.permissions_of(role)
    wrong = []
    for (method, path), key in permissions.ROUTES.items():
        url = _url(path, company.id)
        response = await api.request(
            method, url, json={} if method != "GET" else None, headers=ANON
        )
        refused = response.status_code == 403
        if refused != (key not in allowed):
            wrong.append((method, path, key, response.status_code))
        if refused:
            assert response.headers["content-type"].startswith("application/problem+json")
            assert key in response.json()["detail"]
    assert wrong == []
    # every role may read what needs no key
    assert (
        await api.get("/api/approvals", params={"company_id": str(company.id)}, headers=ANON)
    ).status_code == 200


async def test_the_token_and_admin_emails_are_owners_and_me_says_what_they_may_do(api, db_session):
    me = (await api.get("/api/admin/auth/me")).json()
    assert (me["via"], me["role"]) == ("token", "owner")
    assert set(me["permissions"]) == permissions.ALL

    await _signed_in(api, db_session, ADMIN, None)
    me = (await api.get("/api/admin/auth/me", headers=ANON)).json()
    assert (me["email"], me["role"], set(me["permissions"])) == (ADMIN, "owner", permissions.ALL)

    await _signed_in(api, db_session, "ed@perm.test", "editor")
    me = (await api.get("/api/admin/auth/me", headers=ANON)).json()
    assert (me["role"], sorted(me["permissions"])) == (
        "editor",
        sorted(permissions.permissions_of("editor")),
    )


async def test_owners_let_people_in_and_out(api, db_session, mailbox):
    # somebody who signed up on the site, not on ADMIN_EMAILS: no back office
    outcome = await credentials.register(db_session, "new@perm.test", PASSWORD)
    await credentials.verify_email(db_session, outcome.verify_token)
    await db_session.flush()
    login = {"email": "new@perm.test", "password": PASSWORD}
    assert (await api.post("/api/admin/auth/login", json=login, headers=ANON)).status_code == 403

    # an owner (the token here) lets them in as an editor
    added = await api.post("/api/admin/access", json={"email": "new@perm.test", "role": "editor"})
    assert added.status_code == 201, added.text
    member = added.json()
    assert (member["email"], member["role"], member["granted_by"]["id"]) == (
        "new@perm.test",
        "editor",
        "operator",
    )
    assert (
        await api.post("/api/admin/access", json={"email": "new@perm.test", "role": "viewer"})
    ).status_code == 409
    assert (
        await api.post("/api/admin/access", json={"email": ADMIN, "role": "viewer"})
    ).status_code in (404, 409)
    assert (
        await api.post("/api/admin/access", json={"email": "nobody@perm.test", "role": "viewer"})
    ).status_code == 404

    listed = (await api.get("/api/admin/access")).json()
    assert ADMIN in listed["owners"]
    assert [m["email"] for m in listed["members"]] == ["new@perm.test"]
    assert set(listed["roles"]["owner"]) == permissions.ALL
    assert listed["roles"]["viewer"] == ["self:prefs"]

    # now they open it — and may not manage access
    signed = await api.post("/api/admin/auth/login", json=login, headers=ANON)
    assert signed.status_code == 200, signed.text
    api.cookies.set(ADMIN_COOKIE, signed.cookies[ADMIN_COOKIE])
    assert (await api.get("/api/admin/access", headers=ANON)).status_code == 403

    # their role changes, then they are taken out, and their cookie opens nothing
    reader_id = member["reader_id"]
    assert (await api.put(f"/api/admin/access/{reader_id}", json={"role": "viewer"})).json()[
        "role"
    ] == "viewer"
    assert (await api.get("/api/admin/auth/me", headers=ANON)).json()["role"] == "viewer"
    assert (await api.delete(f"/api/admin/access/{reader_id}")).status_code == 204
    assert (await api.get("/api/admin/auth/me", headers=ANON)).status_code == 401


async def test_an_owner_let_in_cannot_change_their_own_role(api, db_session):
    me = await _signed_in(api, db_session, "own@perm.test", "owner")
    assert (
        await api.put(f"/api/admin/access/{me}", json={"role": "viewer"}, headers=ANON)
    ).status_code == 409
    assert (await api.delete(f"/api/admin/access/{me}", headers=ANON)).status_code == 409


async def test_an_address_not_proven_opens_nothing_even_with_a_role(api, db_session):
    outcome = await credentials.register(db_session, "unproven@perm.test", PASSWORD)
    reader = await db_session.scalar(select(Reader).where(Reader.email == "unproven@perm.test"))
    db_session.add(
        AdminRole(reader_id=reader.id, role="owner", granted_by={"kind": "human", "id": "test"})
    )
    await db_session.flush()
    assert outcome.verify_token
    login = {"email": "unproven@perm.test", "password": PASSWORD}
    assert (await api.post("/api/admin/auth/login", json=login, headers=ANON)).status_code == 403


async def test_a_refused_attempt_is_in_the_record(api, db_session, newsroom_room):
    article_id = await newsroom_room.publish()
    viewer = await _signed_in(api, db_session, "look@perm.test", "viewer")
    refused = await api.post(
        f"/api/articles/{article_id}/unpublish", json={"reason": "x"}, headers=ANON
    )
    assert refused.status_code == 403
    [row] = (
        await db_session.scalars(
            select(AdminAction).where(AdminAction.target_id == str(article_id))
        )
    ).all()
    assert (row.status, row.actor["id"]) == (403, f"admin:{viewer}")


def test_openapi_names_each_routes_key():
    """AD-14: the web app's tests read the keys from openapi.json (conventions.test.ts)."""
    schema = create_app().openapi()
    named = {
        (method.upper(), path): operation["x-permission"]
        for path, operations in schema["paths"].items()
        for method, operation in operations.items()
        if "x-permission" in operation
    }
    assert named == permissions.ROUTES
