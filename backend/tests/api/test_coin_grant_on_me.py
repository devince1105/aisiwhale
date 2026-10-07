"""P3-B over HTTP: ``/api/auth/me`` gives the month's coins, and nothing about coins changes what
it answers or can break it.

The switch is turned on for these tests (it ships off until P3-C); one test checks that off, a
signed-in reader's ``/me`` writes no coins.
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from autora.accounts import Reader, credentials
from autora.accounts.coins import CoinTxn, balance, policy
from autora.company import memberships
from autora.company.organization import add_business_unit, add_product
from autora.db.models import BusinessUnitState, ProductState
from autora.runtime.actor import Actor
from tests.api.conftest import ADMIN
from tests.api.readers import PASSWORD
from tests.conftest import unique_company

OPERATOR = Actor.human("operator")
ME_FIELDS = {"reader_id", "email", "email_verified", "member_until", "tier", "capabilities"}


@pytest.fixture(autouse=True)
def grants_on(monkeypatch):
    monkeypatch.setattr(policy, "MONTHLY_GRANTS_ON", True)


@pytest.fixture
async def company(db_session):
    """A company with a membership product, so an admin can give VIP here."""
    company = await unique_company(db_session, "coins")
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


async def _reader(api, db_session, address: str, *, verified: bool = True):
    outcome = await credentials.register(db_session, address, PASSWORD)
    if verified:
        await credentials.verify_email(db_session, outcome.verify_token)
    await db_session.commit()
    signed = await api.post("/api/auth/login", json={"email": address, "password": PASSWORD})
    assert signed.status_code == 200, signed.text
    return outcome


async def _me(api, company):
    response = await api.get("/api/auth/me", params={"company": company.slug})
    assert response.status_code == 200
    return response.json()


async def _txns(db_session, reader_id) -> int:
    return await db_session.scalar(
        select(func.count()).select_from(CoinTxn).where(CoinTxn.reader_id == reader_id)
    )


async def test_the_first_me_of_the_month_gives_free_coins_and_the_rest_do_not(
    api, db_session, company
):
    outcome = await _reader(api, db_session, "monthly@example.com")
    first = await _me(api, company)
    assert set(first) == ME_FIELDS, "/me answers as it did; coins are not in it"
    assert await balance(db_session, outcome.reader.id) == 50
    for _ in range(3):
        assert await _me(api, company) == first
    assert await _txns(db_session, outcome.reader.id) == 1


async def test_an_unproven_address_gets_its_coins_once_it_is_proven(api, db_session, company):
    outcome = await _reader(api, db_session, "unproven@example.com", verified=False)
    assert (await _me(api, company))["email_verified"] is False
    assert await _txns(db_session, outcome.reader.id) == 0

    proven = await api.post("/api/auth/email/verify", json={"token": outcome.verify_token})
    assert proven.status_code == 204
    assert (await _me(api, company))["email_verified"] is True
    assert await balance(db_session, outcome.reader.id) == 50


async def test_a_comp_gives_vip_coins_on_the_next_me(api, db_session, company):
    outcome = await _reader(api, db_session, "comped@example.com")
    await _me(api, company)
    until = (datetime.now(UTC) + timedelta(days=30)).isoformat()
    comp = await api.post(
        "/api/admin/memberships/comps",
        json={
            "email": "comped@example.com",
            "until": until,
            "reason": "coins",
            "company": company.slug,
        },
    )  # the operator token the api fixture carries
    assert comp.status_code == 201, comp.text
    assert (await _me(api, company))["tier"] == "vip"
    assert await balance(db_session, outcome.reader.id) == 550


async def test_a_grant_that_fails_does_not_fail_me(api, db_session, company, monkeypatch):
    import autora_api.routers.auth as auth_router

    async def broken(*args, **kwargs):
        raise RuntimeError("the ledger is unhappy")

    monkeypatch.setattr(auth_router, "grant_monthly", broken)
    outcome = await _reader(api, db_session, "broken@example.com")
    reader_id = outcome.reader.id  # the router's rollback expires what this shared session holds
    answer = await _me(api, company)
    assert set(answer) == ME_FIELDS and answer["tier"] == "free"
    seen = await db_session.scalar(select(Reader.last_seen_at).where(Reader.id == reader_id))
    assert seen is not None, "last_seen_at was committed before the grant failed"
    assert await _txns(db_session, reader_id) == 0


async def test_off_a_signed_in_me_writes_no_coins(api, db_session, company, monkeypatch):
    monkeypatch.setattr(policy, "MONTHLY_GRANTS_ON", False)
    outcome = await _reader(api, db_session, "off@example.com")
    assert set(await _me(api, company)) == ME_FIELDS
    assert await _txns(db_session, outcome.reader.id) == 0


async def test_the_back_office_s_me_gives_nothing(api, db_session):
    admin = await credentials.register(db_session, ADMIN, PASSWORD)
    await credentials.verify_email(db_session, admin.verify_token)
    await db_session.commit()
    signed = await api.post("/api/admin/auth/login", json={"email": ADMIN, "password": PASSWORD})
    assert signed.status_code == 200, signed.text
    assert (await api.get("/api/admin/auth/me")).status_code == 200
    assert await _txns(db_session, admin.reader.id) == 0


async def test_nobody_signed_in_gets_nothing(api, db_session):
    before = await db_session.scalar(select(func.count()).select_from(CoinTxn))
    assert (await api.get("/api/auth/me")).json() is None
    assert await db_session.scalar(select(func.count()).select_from(CoinTxn)) == before
