"""P2 (D-228, D-231): VIP is given for testing, and nothing is sold.

- Checkout is refused by the API itself — signed in or not, shop configured or not, a month or
  a year — and no order is ever opened. ``SITE_MEMBERSHIP_OPEN`` is the page's business only.
- The catalogue keeps what PayUni was applied with (D-161: NT$30 a month; the year has no price
  yet); the offer says what it costs and that it is not on sale.
- An admin gives a reader VIP (a comp) and ends it; the reader's entitlement — decided by the
  server, returned by ``/api/auth/me`` — follows. Nobody else may give it.
"""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
import pytest
from sqlalchemy import func, select

from autora.accounts import credentials
from autora.accounts.entitlement import CHECKOUT_OPEN, Capability, Entitlement, Tier
from autora.company import memberships
from autora.company.organization import add_business_unit, add_product
from autora.db.models import (
    BusinessUnitState,
    MembershipGrant,
    Order,
    Payment,
    PriceInterval,
    ProductState,
    Transaction,
)
from autora.infra.settings import load_settings
from autora.runtime.actor import Actor
from autora_api.deps import ADMIN_COOKIE, settings_dep
from tests.api.conftest import ADMIN, TOKEN
from tests.api.readers import PASSWORD, sign_in
from tests.conftest import unique_company

OPERATOR = Actor.human("operator")
TESTER = "tester@example.com"
COMPS = "/api/admin/memberships/comps"


@pytest.fixture
async def shop(db_session):
    """A company selling as D-161 left it — NT$30 a month still active — and the D-218 price."""
    company = await unique_company(db_session, "p2shop")
    unit = await add_business_unit(
        db_session, company_id=company.id, key="ai_media", name="AI Media",
        actor=OPERATOR, state=BusinessUnitState.ACTIVE,
    )  # fmt: skip
    product = await add_product(
        db_session, company_id=company.id, key=memberships.PRODUCT_KEY, name="Membership",
        business_unit_id=unit.id, actor=OPERATOR, state=ProductState.LIVE,
    )  # fmt: skip
    await db_session.commit()
    return company, product


@pytest.fixture
async def browser(api, db_settings):
    """A reader's browser, against an app configured as a PAYUNi store (keys present)."""
    app = api._transport.app
    app.dependency_overrides[settings_dep] = lambda: load_settings(
        database_url=db_settings.database_url,
        api_bearer_token=TOKEN,
        admin_emails=[ADMIN],
        payuni_mer_id="TESTSHOP",
        payuni_hash_key="0123456789abcdef0123456789abcdef",
        payuni_hash_iv="0123456789abcdef",
    )
    async with httpx.AsyncClient(transport=api._transport, base_url="http://test") as client:
        yield client


async def _price(db_session, product, amount, interval=PriceInterval.MONTH):
    price = await memberships.add_price(
        db_session, product, amount=Decimal(amount), interval=interval
    )
    await db_session.commit()
    return price


async def _orders(db_session, company):
    """This company's orders: other tests (the acceptance ones) commit orders of their own."""
    return await db_session.scalar(
        select(func.count()).select_from(Order).where(Order.company_id == company.id)
    )


# --- nothing is sold ---


def test_checkout_is_closed_in_p2():
    assert CHECKOUT_OPEN is False
    for tier in Tier:
        granted = Entitlement(tier=tier, is_admin=True)
        assert not granted.can(Capability.BUY_MEMBERSHIP)


@pytest.mark.parametrize(
    ("amount", "interval"), [("30", PriceInterval.MONTH), ("300", PriceInterval.YEAR)]
)
async def test_checkout_is_refused_and_opens_no_order(browser, db_session, shop, amount, interval):
    """D-161's NT$30 a month (or a yearly price, were there one), a signed-in reader, a configured
    shop: still refused, before anything is written."""
    company, product = shop
    await _price(db_session, product, amount, interval)
    await sign_in(browser, "buyer@example.com")

    for interval in ("month", "year"):
        answer = await browser.post(
            "/api/checkout", json={"company": company.slug, "interval": interval}
        )
        assert answer.status_code == 403, answer.text
    assert await _orders(db_session, company) == 0


async def test_checkout_is_refused_to_a_stranger_too(browser, db_session, shop):
    company, product = shop
    await _price(db_session, product, "30")
    answer = await browser.post(
        "/api/checkout", json={"company": company.slug, "interval": "month"}
    )
    assert answer.status_code == 403
    assert await _orders(db_session, company) == 0


async def test_the_offer_is_nt30_a_month_and_not_on_sale(browser, db_session, shop):
    """The catalogue as PayUni was applied with (D-161, D-231): shown, not sold."""
    company, product = shop
    await _price(db_session, product, "30")
    ask = {"company": company.slug}

    month = (await browser.get("/api/checkout/offer", params=ask | {"interval": "month"})).json()
    year = (await browser.get("/api/checkout/offer", params=ask | {"interval": "year"})).json()

    assert Decimal(month["amount"]) == Decimal("30")
    assert (month["currency"], month["interval"], month["available"]) == ("TWD", "month", False)
    assert (Decimal(year["amount"]), year["available"]) == (Decimal(0), False), (
        "the year has no price in the catalogue yet; the page shows NT$300 faded (D-161)"
    )


# --- VIP given by an admin ---


async def _tester(db_session, address=TESTER):
    outcome = await credentials.register(db_session, address, PASSWORD)
    await db_session.commit()
    return outcome.reader


async def _grant(api, company, *, email=TESTER, days=30, reason="internal test", headers=None):
    until = (datetime.now(UTC) + timedelta(days=days)).isoformat()
    return await api.post(
        COMPS,
        json={"email": email, "until": until, "reason": reason, "company": company.slug},
        headers=headers,
    )


async def _me(browser, company):
    return (await browser.get("/api/auth/me", params={"company": company.slug})).json()


async def test_an_admin_gives_vip_and_the_reader_has_it(api, browser, db_session, shop):
    company, _ = shop
    reader = await _tester(db_session)
    await browser.post("/api/auth/login", json={"email": TESTER, "password": PASSWORD})
    before = await _me(browser, company)
    assert before["tier"] == "free" and "read_vip_articles" not in before["capabilities"]

    granted = await _grant(api, company)

    assert granted.status_code == 201, granted.text
    body = granted.json()
    assert body["reader_id"] == str(reader.id) and body["email"] == TESTER
    assert body["source"] == "admin_comp" and body["running"] is True
    assert body["actor"] == {"kind": "human", "id": "operator"}
    after = await _me(browser, company)
    assert after["tier"] == "vip" and after["member_until"] is not None
    assert "read_vip_articles" in after["capabilities"]
    assert "buy_membership" not in after["capabilities"]


async def test_a_comp_given_through_the_api_sells_nothing(api, db_session, shop):
    company, _ = shop
    await _tester(db_session)
    assert (await _grant(api, company)).status_code == 201
    for model in (Order, Payment, Transaction):
        count = await db_session.scalar(
            select(func.count()).select_from(model).where(model.company_id == company.id)
        )
        assert count == 0, model.__name__


async def test_ending_a_comp_takes_vip_away_and_keeps_the_record(api, browser, db_session, shop):
    company, _ = shop
    await _tester(db_session)
    await browser.post("/api/auth/login", json={"email": TESTER, "password": PASSWORD})
    grant_id = (await _grant(api, company)).json()["id"]

    ended = await api.post(
        f"{COMPS}/{grant_id}/revoke", json={"reason": "test finished"},
        params={"company": company.slug},
    )  # fmt: skip

    assert ended.status_code == 200, ended.text
    body = ended.json()
    assert body["running"] is False and body["revoke_reason"] == "test finished"
    assert body["revoked_by"] == {"kind": "human", "id": "operator"}
    assert (await _me(browser, company))["tier"] == "free"
    again = await api.post(
        f"{COMPS}/{grant_id}/revoke", json={"reason": "again"}, params={"company": company.slug}
    )
    assert again.status_code == 409
    listed = (await api.get(COMPS, params={"company": company.slug})).json()
    assert [comp["id"] for comp in listed] == [grant_id], "the history stays"
    running = (await api.get(COMPS, params={"company": company.slug, "running": True})).json()
    assert running == []
    one = await api.get(f"{COMPS}/{grant_id}", params={"company": company.slug})
    assert one.json()["revoke_reason"] == "test finished"


async def test_an_admin_signed_in_is_recorded_by_id_never_by_address(
    api, browser, db_session, shop
):
    company, _ = shop
    await _tester(db_session)
    admin = await credentials.register(db_session, ADMIN, PASSWORD)
    await credentials.verify_email(db_session, admin.verify_token)
    await db_session.commit()
    signed_in = await browser.post(
        "/api/admin/auth/login", json={"email": ADMIN, "password": PASSWORD}
    )
    browser.cookies.set(ADMIN_COOKIE, signed_in.cookies[ADMIN_COOKIE])

    granted = await _grant(browser, company)

    assert granted.status_code == 201, granted.text
    assert granted.json()["actor"] == {"kind": "human", "id": f"admin:{admin.reader.id}"}
    row = await db_session.get(MembershipGrant, uuid.UUID(granted.json()["id"]))
    assert ADMIN not in str(row.actor)


async def test_nobody_else_may_give_vip(api, browser, db_session, shop):
    """A reader signed in to the site, or nobody: 401, and nothing is written."""
    company, _ = shop
    await _tester(db_session)
    assert (await _grant(browser, company)).status_code == 401
    await sign_in(browser, "someone@example.com")
    assert (await _grant(browser, company)).status_code == 401
    count = await db_session.scalar(
        select(func.count())
        .select_from(MembershipGrant)
        .where(MembershipGrant.company_id == company.id)
    )
    assert count == 0


async def test_a_comp_needs_a_reader_a_future_end_and_a_reason(api, db_session, shop):
    company, _ = shop
    await _tester(db_session)
    assert (await _grant(api, company, email="nobody@example.com")).status_code == 404
    assert (await _grant(api, company, days=-1)).status_code == 422
    assert (await _grant(api, company, reason="")).status_code == 422
    assert (await _grant(api, company, reason="   ")).status_code == 422


# --- what the server says a visitor may do ---


def test_what_each_tier_may_do():
    public = Entitlement(tier=Tier.PUBLIC)
    free = Entitlement(tier=Tier.FREE)
    vip = Entitlement(tier=Tier.VIP)
    admin = Entitlement(tier=Tier.FREE, is_admin=True)

    assert public.capabilities == frozenset()
    assert free.capabilities == {Capability.READ_SIGN_IN_SECTIONS, Capability.WATCHLIST}
    assert vip.capabilities == free.capabilities | {Capability.READ_VIP_ARTICLES}
    assert admin.can(Capability.ADMIN) and not admin.can(Capability.READ_VIP_ARTICLES), (
        "an admin opens the back office; VIP articles take a membership like anybody's"
    )


async def test_nobody_signed_in_is_nobody(browser):
    assert (await browser.get("/api/auth/me")).json() is None
