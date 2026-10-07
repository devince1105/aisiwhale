"""P3-C-2: Whale Coins in the back office over HTTP — a wallet, an adjustment, the check.

The ``api`` client carries the operator token; ``browser`` is a client with no token, for an
admin signed in to the back office (their own actor) or a reader (refused).
"""

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import func, select, text

from autora.accounts import credentials
from autora.accounts.coins import CoinTxn, TxnKind, grant
from autora.company import memberships
from autora.company.organization import add_business_unit, add_product
from autora.db.models import AdminAction, BusinessUnitState, ProductState
from autora.runtime.actor import Actor
from autora_api.deps import ADMIN_COOKIE
from tests.api.conftest import ADMIN
from tests.api.readers import PASSWORD, sign_in
from tests.conftest import unique_company

OPERATOR = Actor.human("operator")
SYSTEM = Actor.system("admin-coins-test")
READER = "wallet-owner@example.com"
ADJUST = "/api/admin/coins/adjustments"


@pytest.fixture
async def company(db_session):
    company = await unique_company(db_session, "adminco")
    unit = await add_business_unit(
        db_session, company_id=company.id, key="ai_media", name="AI Media",
        actor=OPERATOR, state=BusinessUnitState.ACTIVE,
    )  # fmt: skip
    await add_product(
        db_session, company_id=company.id, key=memberships.PRODUCT_KEY, name="Membership",
        business_unit_id=unit.id, actor=OPERATOR, state=ProductState.LIVE,
    )  # fmt: skip
    await db_session.commit()
    # plain values: a refused adjustment rolls the shared session back, which would expire the row
    return SimpleNamespace(id=company.id, slug=company.slug)


@pytest.fixture
async def browser(api):
    async with httpx.AsyncClient(transport=api._transport, base_url="http://test") as client:
        yield client


@pytest.fixture
async def reader(db_session):
    outcome = await credentials.register(db_session, READER, PASSWORD)
    await db_session.commit()
    return outcome.reader.id


async def _fill(db_session, reader_id, coins: int) -> None:
    await grant(
        db_session, reader_id, requested=coins, cap=coins, kind=TxnKind.PROMOTION_GRANT,
        idempotency_key=f"promo:setup:{reader_id}", actor=SYSTEM,
    )  # fmt: skip
    await db_session.commit()


def _body(company, **over):
    return {
        "email": READER,
        "amount": 20,
        "reason": "goodwill",
        "override_cap": False,
        "request_id": str(uuid.uuid4()),
        "company": company.slug,
    } | over


async def _txns(db_session, **where) -> int:
    stmt = select(func.count()).select_from(CoinTxn)
    for key, value in where.items():
        stmt = stmt.where(getattr(CoinTxn, key) == value)
    return await db_session.scalar(stmt)


# --- who may ------------------------------------------------------------------------------------


async def test_nobody_but_the_back_office_may_look_or_adjust(browser, db_session, reader, company):
    assert (
        await browser.get("/api/admin/coins/wallet", params={"email": READER})
    ).status_code == 401
    assert (await browser.post(ADJUST, json=_body(company))).status_code == 401
    assert (await browser.get("/api/admin/coins/reconcile")).status_code == 401
    await sign_in(browser, "just-a-reader@example.com")  # a reader's cookie opens nothing here
    assert (await browser.post(ADJUST, json=_body(company))).status_code == 401
    assert await _txns(db_session, reader_id=reader) == 0


async def test_an_address_nobody_has_is_404(api, company):
    assert (
        await api.get("/api/admin/coins/wallet", params={"email": "nobody@example.com"})
    ).status_code == 404
    assert (
        await api.post(ADJUST, json=_body(company, email="nobody@example.com"))
    ).status_code == 404


# --- looking ------------------------------------------------------------------------------------


async def test_a_wallet_shows_the_tier_s_cap_and_everything_about_each_movement(
    api, db_session, reader, company
):
    await _fill(db_session, reader, 30)
    response = await api.get(
        "/api/admin/coins/wallet", params={"email": READER, "company": company.slug}
    )
    assert response.status_code == 200, response.text
    wallet = response.json()
    assert (wallet["email"], wallet["tier"], wallet["cap"], wallet["balance"]) == (
        READER,
        "free",
        100,
        30,
    )
    (movement,) = wallet["history"]["items"]
    assert movement["idempotency_key"] == f"promo:setup:{reader}"
    assert movement["actor"] == {"kind": "system", "id": "admin-coins-test"}
    assert wallet["history"]["total"] == 1


async def test_looking_and_checking_write_nothing(api, db_session, reader, company):
    await _fill(db_session, reader, 30)
    before = await _txns(db_session)
    await api.get("/api/admin/coins/wallet", params={"email": READER, "company": company.slug})
    report = (await api.get("/api/admin/coins/reconcile")).json()
    assert report["ok"] is True, report["problems"]
    assert report["totals"]["entries"] == 0
    assert await _txns(db_session) == before
    assert await db_session.scalar(
        select(func.count()).select_from(AdminAction).where(AdminAction.route.like("%coins%"))
    ) == 0  # fmt: skip


async def test_the_check_names_what_does_not_add_up(api, db_session, reader, company):
    await _fill(db_session, reader, 30)
    await db_session.execute(
        text("UPDATE coin_wallets SET balance = balance + 1 WHERE reader_id = :r"), {"r": reader}
    )  # the commit-time check never runs in this rolled-back test transaction
    report = (await api.get("/api/admin/coins/reconcile")).json()
    assert report["ok"] is False
    assert any(str(reader) in problem for problem in report["problems"])


# --- adjusting ----------------------------------------------------------------------------------


async def test_an_adjustment_is_made_by_the_admin_signed_in_never_by_the_reader(
    browser, db_session, reader, company
):
    """The actor is whoever require_operator let in: the admin's own id, not the wallet's."""
    admin = await credentials.register(db_session, ADMIN, PASSWORD)
    await credentials.verify_email(db_session, admin.verify_token)
    await db_session.commit()
    signed_in = await browser.post(
        "/api/admin/auth/login", json={"email": ADMIN, "password": PASSWORD}
    )
    browser.cookies.set(ADMIN_COOKIE, signed_in.cookies[ADMIN_COOKIE])

    response = await browser.post(ADJUST, json=_body(company))

    assert response.status_code == 201, response.text
    movement = response.json()
    assert movement["actor"] == {"kind": "human", "id": f"admin:{admin.reader.id}"}
    assert str(reader) not in str(movement["actor"])
    assert ADMIN not in str(movement["actor"]), "by id, never by address"
    txn = await db_session.get(CoinTxn, uuid.UUID(movement["id"]))
    assert txn.reader_id == reader, "the coins are the reader's; the act is the admin's"


async def test_up_to_the_tier_s_cap_and_past_it_only_when_overridden(
    api, db_session, reader, company
):
    await _fill(db_session, reader, 90)
    within = await api.post(ADJUST, json=_body(company, amount=10))
    assert within.status_code == 201, within.text
    assert (within.json()["balance_after"], within.json()["cap"]) == (100, 100)
    assert within.json()["meta"] == {"tier": "free", "tier_cap": 100, "override_cap": False}

    past = await api.post(ADJUST, json=_body(company, amount=1))
    assert past.status_code == 422
    assert "cap" in past.text
    assert await _txns(db_session, reader_id=reader, kind="ADMIN_ADJUSTMENT") == 1

    over = await api.post(ADJUST, json=_body(company, amount=1, override_cap=True))
    assert over.status_code == 201, over.text
    assert (over.json()["balance_after"], over.json()["cap"]) == (101, None)
    assert over.json()["meta"]["override_cap"] is True


async def test_a_vip_s_cap_is_a_vip_s(api, db_session, reader, company):
    until = (datetime.now(UTC) + timedelta(days=30)).isoformat()
    comp = await api.post(
        "/api/admin/memberships/comps",
        json={"email": READER, "until": until, "reason": "cap test", "company": company.slug},
    )
    assert comp.status_code == 201, comp.text
    response = await api.post(ADJUST, json=_body(company, amount=1000))
    assert response.status_code == 201, response.text
    assert (response.json()["cap"], response.json()["meta"]["tier"]) == (1000, "vip")


async def test_down_never_below_zero(api, db_session, reader, company):
    await _fill(db_session, reader, 5)
    assert (await api.post(ADJUST, json=_body(company, amount=-6))).status_code == 422
    down = await api.post(ADJUST, json=_body(company, amount=-5))
    assert down.status_code == 201, down.text
    assert (down.json()["balance_after"], down.json()["cap"]) == (0, None)


async def test_the_same_request_is_one_adjustment_and_another_under_its_id_is_refused(
    api, db_session, reader, company
):
    body = _body(company, amount=7)
    first = await api.post(ADJUST, json=body)
    again = await api.post(ADJUST, json=body)
    assert (first.status_code, again.status_code) == (201, 200)
    assert again.json()["id"] == first.json()["id"]
    other = await api.post(ADJUST, json=body | {"amount": 8})
    assert other.status_code == 409
    assert await _txns(db_session, reader_id=reader, kind="ADMIN_ADJUSTMENT") == 1


@pytest.mark.parametrize(
    "over",
    [{"amount": 0}, {"amount": 10_001}, {"amount": -10_001}, {"reason": "   "}, {"reason": ""}],
)
async def test_what_is_not_an_adjustment_is_refused(api, db_session, reader, company, over):
    assert (await api.post(ADJUST, json=_body(company, **over))).status_code == 422
    assert await _txns(db_session, reader_id=reader) == 0


async def test_the_largest_adjustment_allowed_is_ten_thousand(api, db_session, reader, company):
    response = await api.post(ADJUST, json=_body(company, amount=10_000, override_cap=True))
    assert response.status_code == 201, response.text


async def test_an_adjustment_is_in_the_back_office_s_record(api, db_session, reader, company):
    response = await api.post(ADJUST, json=_body(company, reason="audit me"))
    assert response.status_code == 201
    (row,) = (
        await db_session.scalars(select(AdminAction).where(AdminAction.route == ADJUST))
    ).all()
    assert row.actor == {"kind": "human", "id": "operator"}
    assert (row.method, row.status) == ("POST", 201)
    assert row.input["body"]["reason"] == "audit me"
    assert row.input["body"]["email"] == READER
