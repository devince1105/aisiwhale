"""P3-C: a signed-in reader's Whale Coins over HTTP — ``GET /api/me/coins``, read only.

The month's status is the grant's own (``coins.this_month``); these tests write coins straight
into the ledger to have something to show, and check what the page may and may not say.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from autora.accounts import credentials
from autora.accounts.coins import (
    CoinTxn,
    TxnKind,
    adjust,
    grant,
    grant_monthly,
    policy,
    spend,
)
from autora.accounts.entitlement import Tier
from autora.company import memberships
from autora.company.organization import add_business_unit, add_product
from autora.db.models import BusinessUnitState, ProductState
from autora.runtime.actor import Actor
from tests.api.readers import PASSWORD
from tests.conftest import unique_company

OPERATOR = Actor.human("operator")
SYSTEM = Actor.system("coins-api-test")
ADMIN = Actor.human("admin:someone")
MOVEMENT_FIELDS = {
    "id",
    "kind",
    "amount",
    "balance_after",
    "occurred_at",
    "month",
    "ref_type",
    "ref_id",
}


@pytest.fixture
async def company(db_session):
    company = await unique_company(db_session, "wallet")
    unit = await add_business_unit(
        db_session, company_id=company.id, key="ai_media", name="AI Media",
        actor=OPERATOR, state=BusinessUnitState.ACTIVE,
    )  # fmt: skip
    await add_product(
        db_session, company_id=company.id, key=memberships.PRODUCT_KEY, name="Membership",
        business_unit_id=unit.id, actor=OPERATOR, state=ProductState.LIVE,
    )  # fmt: skip
    await db_session.commit()
    return company


async def _signed_in(api, db_session, address: str) -> uuid.UUID:
    outcome = await credentials.register(db_session, address, PASSWORD)
    await credentials.verify_email(db_session, outcome.verify_token)
    await db_session.commit()
    signed = await api.post("/api/auth/login", json={"email": address, "password": PASSWORD})
    assert signed.status_code == 200, signed.text
    return outcome.reader.id


async def _wallet(api, company, **params):
    response = await api.get("/api/me/coins", params={"company": company.slug, **params})
    assert response.status_code == 200, response.text
    return response.json()


async def _txns(db_session) -> int:
    return await db_session.scalar(select(func.count()).select_from(CoinTxn))


async def test_nobody_signed_in_has_no_wallet(api):
    assert (await api.get("/api/me/coins")).status_code == 401


async def test_a_new_reader_holds_nothing_and_the_month_is_not_given(api, db_session, company):
    await _signed_in(api, db_session, "new@example.com")
    wallet = await _wallet(api, company)
    month = policy.month_of(datetime.now(UTC))
    assert wallet == {
        "balance": 0,
        "tier": "free",
        "monthly": {
            "amount": 50,
            "cap": 300,
            "month": month,
            "granted": False,
            "grants_on": True,  # D-247: on (D-238 shipped it off)
        },
        "history": {"items": [], "next_cursor": None, "total": 0},
    }


async def test_the_page_says_when_grants_are_on_and_when_the_month_was_given(
    api, db_session, company, monkeypatch
):
    monkeypatch.setattr(policy, "MONTHLY_GRANTS_ON", True)
    reader = await _signed_in(api, db_session, "given@example.com")
    assert (await _wallet(api, company))["monthly"]["grants_on"] is True
    await grant_monthly(db_session, reader, tier=Tier.FREE, email_verified=True)
    await db_session.commit()
    wallet = await _wallet(api, company)
    assert wallet["monthly"]["granted"] is True
    assert wallet["balance"] == 50
    (movement,) = wallet["history"]["items"]
    assert (movement["kind"], movement["amount"], movement["month"]) == (
        "MONTHLY_GRANT",
        50,
        policy.month_of(datetime.now(UTC)),
    )


async def test_movements_come_newest_first_a_page_at_a_time(api, db_session, company):
    reader = await _signed_in(api, db_session, "pages@example.com")
    await grant(
        db_session, reader, requested=80, cap=100, kind=TxnKind.PROMOTION_GRANT,
        idempotency_key=f"promo:pages:{reader}", actor=SYSTEM,
    )  # fmt: skip
    await spend(db_session, reader, amount=5, idempotency_key=f"spend:pages:{reader}", actor=SYSTEM)
    await adjust(
        db_session, reader, amount=-3, reason="a private note", cap=None,
        idempotency_key=f"adj:{uuid.uuid4().hex}", actor=ADMIN,
    )  # fmt: skip
    await db_session.commit()

    first = await _wallet(api, company, limit=2)
    assert first["balance"] == 72
    assert first["history"]["total"] == 3
    assert [m["kind"] for m in first["history"]["items"]] == ["ADMIN_ADJUSTMENT", "SPEND"]
    assert first["history"]["next_cursor"]
    rest = await _wallet(api, company, limit=2, cursor=first["history"]["next_cursor"])
    assert [m["kind"] for m in rest["history"]["items"]] == ["PROMOTION_GRANT"]
    assert rest["history"]["next_cursor"] is None


async def test_a_reader_sees_what_moved_and_not_who_or_why(api, db_session, company):
    reader = await _signed_in(api, db_session, "private@example.com")
    await adjust(
        db_session, reader, amount=10, cap=100, reason="internal: goodwill for bug #12",
        idempotency_key=f"adj:{uuid.uuid4().hex}", actor=ADMIN,
    )  # fmt: skip
    await db_session.commit()
    response = await api.get("/api/me/coins", params={"company": company.slug})
    (movement,) = response.json()["history"]["items"]
    assert set(movement) == MOVEMENT_FIELDS
    assert (movement["kind"], movement["amount"], movement["balance_after"]) == (
        "ADMIN_ADJUSTMENT",
        10,
        10,
    )
    for secret in ("goodwill", "admin:someone", "adj:", "override_cap"):
        assert secret not in response.text


async def test_a_month_capped_to_nothing_is_listed(api, db_session, company, monkeypatch):
    monkeypatch.setattr(policy, "MONTHLY_GRANTS_ON", True)
    reader = await _signed_in(api, db_session, "capped@example.com")
    await grant(
        db_session, reader, requested=300, cap=300, kind=TxnKind.PROMOTION_GRANT,
        idempotency_key=f"promo:capped:{reader}", actor=SYSTEM,
    )  # fmt: skip
    await grant_monthly(db_session, reader, tier=Tier.FREE, email_verified=True)
    await db_session.commit()
    wallet = await _wallet(api, company)
    assert wallet["monthly"]["granted"] is True
    assert [(m["kind"], m["amount"]) for m in wallet["history"]["items"]] == [
        ("MONTHLY_GRANT", 0),
        ("PROMOTION_GRANT", 300),
    ]


async def test_looking_writes_no_coins(api, db_session, company):
    await _signed_in(api, db_session, "looker@example.com")
    before = await _txns(db_session)
    for _ in range(3):
        await _wallet(api, company)
    assert await _txns(db_session) == before


async def test_a_vip_s_month_is_vip_s(api, db_session, company):
    await _signed_in(api, db_session, "vip-wallet@example.com")
    until = (datetime.now(UTC) + timedelta(days=30)).isoformat()
    comp = await api.post(
        "/api/admin/memberships/comps",
        json={"email": "vip-wallet@example.com", "until": until, "reason": "wallet test",
              "company": company.slug},
    )  # fmt: skip
    assert comp.status_code == 201, comp.text
    wallet = await _wallet(api, company)
    assert wallet["tier"] == "vip"
    assert (wallet["monthly"]["amount"], wallet["monthly"]["cap"]) == (500, 3000)


async def test_a_signed_in_reader_may_look_at_coins(api, db_session, company):
    await _signed_in(api, db_session, "may@example.com")
    me = (await api.get("/api/auth/me", params={"company": company.slug})).json()
    assert "coins" in me["capabilities"]


async def test_a_bad_cursor_is_refused(api, db_session, company):
    await _signed_in(api, db_session, "cursor@example.com")
    response = await api.get(
        "/api/me/coins", params={"company": company.slug, "cursor": "not-a-cursor"}
    )
    assert response.status_code == 400
