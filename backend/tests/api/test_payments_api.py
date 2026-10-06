"""T-702: buying a year over HTTP, from the checkout form to the notification that pays.

**The P8 path, kept working while it is closed.** P2 closes checkout (D-218,
``accounts.entitlement.CHECKOUT_OPEN``); these tests open it for themselves so the payment path
P8 will reopen stays tested. That P2 refuses it is ``test_membership_p2_api``.

PAYUNi's own servers are never contacted here. The notifications are sealed with the same shop
secrets the app is configured with, which is exactly what PAYUNi does — so what these tests
exercise is every check the handler makes, including the ones that decide a message is not
PAYUNi's. What they cannot show is that PAYUNi agrees with our reading of its documentation;
only a sandbox store can, and the crypto is cross-checked against an independent implementation
in ``tests/infra/test_payuni.py``.
"""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import func, select

from autora.company import memberships, orders
from autora.company.organization import add_business_unit, add_product
from autora.db.models import (
    BusinessUnitState,
    Company,
    Order,
    OrderState,
    Payment,
    PaymentEvent,
    Price,
    PriceInterval,
    ProductState,
)
from autora.infra.payments import payuni
from autora.infra.settings import load_settings
from autora.runtime.actor import Actor
from autora_api.deps import settings_dep
from tests.api.readers import sign_in_id

OPERATOR = Actor.human("operator")
ADDRESS = "buyer@example.com"

MER_ID = "TESTSHOP"
KEY = "0123456789abcdef0123456789abcdef"
IV = "0123456789abcdef"


@pytest.fixture(autouse=True)
def p8_checkout_open(monkeypatch):
    """Checkout as P8 will open it: these tests are that path, not P2's closed door."""
    from autora.accounts import entitlement

    monkeypatch.setattr(entitlement, "CHECKOUT_OPEN", True)


@pytest.fixture
async def shop(api, db_settings):
    """The app, configured as a PAYUNi store. The secrets are this test's, not anybody's."""
    app = api._transport.app
    app.dependency_overrides[settings_dep] = lambda: load_settings(
        database_url=db_settings.database_url,
        api_bearer_token="test-operator-token",
        payuni_mer_id=MER_ID,
        payuni_hash_key=KEY,
        payuni_hash_iv=IV,
    )
    async with httpx.AsyncClient(transport=api._transport, base_url="http://test") as client:
        yield client


@pytest.fixture
async def unconfigured(api, db_settings):
    """The same app with no store: a site that has not applied for one yet.

    The three ids are cleared explicitly rather than left out, because a developer running the
    suite has a real ``.env`` and this test would otherwise pass or fail depending on whether
    they happen to have a PAYUNi store.
    """
    app = api._transport.app
    app.dependency_overrides[settings_dep] = lambda: load_settings(
        database_url=db_settings.database_url,
        api_bearer_token="test-operator-token",
        payuni_mer_id=None,
        payuni_hash_key=None,
        payuni_hash_iv=None,
    )
    async with httpx.AsyncClient(transport=api._transport, base_url="http://test") as client:
        yield client


@pytest.fixture
async def company(db_session):
    """The company, as plain values.

    Deliberately not the ORM row: the handlers commit, a commit expires every loaded object, and
    reading ``company.slug`` afterwards would quietly go back to the database from a place that
    cannot await. What a test needs from a company is an id and a slug.
    """
    row = Company(name="Autora Test", slug=f"t{uuid.uuid4().hex[:8]}")
    db_session.add(row)
    await db_session.flush()
    return SimpleNamespace(id=row.id, slug=row.slug)


async def _for_sale(db_session, company, amount="360", month=None):
    unit = await add_business_unit(
        db_session, company_id=company.id, key="ai_media", name="AI Media",
        actor=OPERATOR, state=BusinessUnitState.ACTIVE,
    )  # fmt: skip
    product = await add_product(
        db_session, company_id=company.id, key=memberships.PRODUCT_KEY, name="Membership",
        business_unit_id=unit.id, actor=OPERATOR, state=ProductState.LIVE,
    )  # fmt: skip
    price = await memberships.add_price(db_session, product, amount=Decimal(amount))
    if month is not None:
        await memberships.add_price(
            db_session, product, amount=Decimal(month), interval=PriceInterval.MONTH
        )
    await db_session.commit()
    return price


async def _sign_in(client, mailbox, address=ADDRESS):
    return await sign_in_id(client, address)


def _notification(mer_trade_no, *, amount="360", trade_status=payuni.TRADE_PAID, trade_no=None):
    """What PAYUNi posts, sealed the way PAYUNi seals it."""
    fields = {
        "Status": payuni.SUCCEEDED,
        "Message": "交易成功",
        "MerID": MER_ID,
        "MerTradeNo": mer_trade_no,
        "TradeNo": trade_no or f"UNI{uuid.uuid4().hex[:12]}",
        "TradeAmt": str(amount),
        "TradeStatus": trade_status,
        "PaymentType": "1",
    }
    return payuni.seal(fields, key=KEY, iv=IV).as_form(MER_ID) | {"Status": payuni.SUCCEEDED}


async def _member_until(client, company):
    """Always with the slug: without one the API answers for the oldest company it can find,
    which in a suite that has made several is somebody else's."""
    return (await client.get("/api/auth/me", params={"company": company.slug})).json()[
        "member_until"
    ]


# --- what a year costs --------------------------------------------------------------------------


async def test_a_site_with_nothing_for_sale_says_so_rather_than_failing(shop, company):
    offer = (await shop.get("/api/checkout/offer", params={"company": company.slug})).json()
    assert offer["available"] is False


async def test_the_offer_is_the_price_that_was_set(shop, db_session, company):
    await _for_sale(db_session, company, amount="360")
    offer = (await shop.get("/api/checkout/offer", params={"company": company.slug})).json()
    assert Decimal(offer.pop("amount")) == Decimal("360")
    assert offer == {"currency": "TWD", "interval": "year", "available": True}


async def test_a_month_and_a_year_are_each_their_own_price(shop, db_session, company):
    """D-034: both on sale at once, and asking for one never answers with the other."""
    await _for_sale(db_session, company, amount="330", month="30")
    ask = {"company": company.slug}
    year = (await shop.get("/api/checkout/offer", params=ask | {"interval": "year"})).json()
    month = (await shop.get("/api/checkout/offer", params=ask | {"interval": "month"})).json()
    assert (Decimal(year["amount"]), year["interval"]) == (Decimal("330"), "year")
    assert (Decimal(month["amount"]), month["interval"]) == (Decimal("30"), "month")
    assert Decimal((await shop.get("/api/checkout/offer", params=ask)).json()["amount"]) == 330


async def test_a_month_that_is_not_for_sale_is_not_the_year_instead(shop, db_session, company):
    await _for_sale(db_session, company)
    offer = (
        await shop.get("/api/checkout/offer", params={"company": company.slug, "interval": "month"})
    ).json()
    assert offer["available"] is False
    assert offer["interval"] == "month"


# --- starting a checkout ------------------------------------------------------------------------


async def test_nobody_buys_a_membership_without_signing_in(shop, db_session, company):
    await _for_sale(db_session, company)
    response = await shop.post("/api/checkout", json={"company": company.slug})
    assert response.status_code == 401


async def test_a_site_without_a_store_says_payments_are_not_configured(
    unconfigured, db_session, company, mailbox
):
    await _for_sale(db_session, company)
    await _sign_in(unconfigured, mailbox)
    response = await unconfigured.post("/api/checkout", json={"company": company.slug})
    assert response.status_code == 503


async def test_checkout_hands_back_a_form_and_writes_a_pending_order(
    shop, db_session, company, mailbox
):
    await _for_sale(db_session, company)
    await _sign_in(shop, mailbox)

    checkout = (await shop.post("/api/checkout", json={"company": company.slug})).json()
    assert checkout["url"].endswith("/upp")
    assert Decimal(checkout["amount"]) == Decimal("360")
    assert set(checkout["fields"]) == {"MerID", "Version", "EncryptInfo", "HashInfo"}

    order = await db_session.get(Order, uuid.UUID(checkout["order_id"]))
    assert order.state == OrderState.PENDING.value
    assert order.mer_trade_no == checkout["mer_trade_no"]
    assert await _member_until(shop, company) is None, "an order is not a payment"


async def test_the_form_carries_the_order_and_can_be_opened_with_the_shop_s_key(
    shop, db_session, company, mailbox
):
    """The envelope is not decoration: PAYUNi will read these fields out of it."""
    await _for_sale(db_session, company)
    await _sign_in(shop, mailbox)
    checkout = (await shop.post("/api/checkout", json={"company": company.slug})).json()

    sent = payuni.unseal(
        checkout["fields"]["EncryptInfo"], checkout["fields"]["HashInfo"], key=KEY, iv=IV
    )
    assert sent["MerTradeNo"] == checkout["mer_trade_no"]
    assert sent["TradeAmt"] == "360"
    assert sent["UsrMail"] == ADDRESS
    assert sent["NotifyURL"].endswith("/api/payments/payuni/notify")


async def test_a_month_is_ordered_at_the_month_s_price_and_buys_a_month(
    shop, db_session, company, mailbox
):
    await _for_sale(db_session, company, amount="330", month="30")
    await _sign_in(shop, mailbox)
    checkout = (
        await shop.post("/api/checkout", json={"company": company.slug, "interval": "month"})
    ).json()
    sent = payuni.unseal(
        checkout["fields"]["EncryptInfo"], checkout["fields"]["HashInfo"], key=KEY, iv=IV
    )
    assert (sent["TradeAmt"], sent["ProdDesc"]) == ("30", "艾矽鯨會員一個月")

    await shop.post(
        "/api/payments/payuni/notify", data=_notification(checkout["mer_trade_no"], amount="30")
    )
    until = datetime.fromisoformat(await _member_until(shop, company))
    now = datetime.now(UTC)
    assert now + timedelta(days=27) < until < now + timedelta(days=32), "a month, not a year"


async def test_an_interval_nobody_sells_is_refused(shop, db_session, company, mailbox):
    await _for_sale(db_session, company)
    await _sign_in(shop, mailbox)
    week = await shop.post("/api/checkout", json={"company": company.slug, "interval": "week"})
    month = await shop.post("/api/checkout", json={"company": company.slug, "interval": "month"})
    assert week.status_code == 422
    assert month.status_code == 404


async def test_nothing_is_for_sale_is_a_404_not_an_order(shop, company, mailbox):
    await _sign_in(shop, mailbox)
    response = await shop.post("/api/checkout", json={"company": company.slug})
    assert response.status_code == 404


# --- the notification ---------------------------------------------------------------------------


async def test_a_paid_notification_buys_the_year(shop, db_session, company, mailbox):
    await _for_sale(db_session, company)
    await _sign_in(shop, mailbox)
    checkout = (await shop.post("/api/checkout", json={"company": company.slug})).json()
    assert await _member_until(shop, company) is None

    response = await shop.post(
        "/api/payments/payuni/notify", data=_notification(checkout["mer_trade_no"])
    )
    assert response.status_code == 200
    assert response.text == "1|OK"
    assert await _member_until(shop, company) is not None

    order = await db_session.get(Order, uuid.UUID(checkout["order_id"]))
    await db_session.refresh(order)
    assert order.state == OrderState.PAID.value
    assert order.payment_id is not None


async def test_the_same_notification_again_changes_nothing(shop, db_session, company, mailbox):
    await _for_sale(db_session, company)
    await _sign_in(shop, mailbox)
    checkout = (await shop.post("/api/checkout", json={"company": company.slug})).json()
    form = _notification(checkout["mer_trade_no"])

    first = await shop.post("/api/payments/payuni/notify", data=form)
    until = await _member_until(shop, company)
    again = await shop.post("/api/payments/payuni/notify", data=form)

    assert (first.text, again.text) == ("1|OK", "1|OK")
    assert await _member_until(shop, company) == until
    assert await _count(db_session, Payment, Payment.company_id == company.id) == 1


async def test_a_notification_nobody_sealed_is_refused(shop, db_session, company, mailbox):
    await _for_sale(db_session, company)
    await _sign_in(shop, mailbox)
    checkout = (await shop.post("/api/checkout", json={"company": company.slug})).json()

    forged = _notification(checkout["mer_trade_no"]) | {"HashInfo": "0" * 64}
    response = await shop.post("/api/payments/payuni/notify", data=forged)

    assert response.status_code == 400
    assert await _member_until(shop, company) is None


async def test_a_notification_that_says_a_different_amount_is_refused(
    shop, db_session, company, mailbox
):
    await _for_sale(db_session, company, amount="360")
    await _sign_in(shop, mailbox)
    checkout = (await shop.post("/api/checkout", json={"company": company.slug})).json()

    response = await shop.post(
        "/api/payments/payuni/notify", data=_notification(checkout["mer_trade_no"], amount="1")
    )
    assert response.status_code == 400
    assert await _member_until(shop, company) is None
    assert await _count(db_session, Payment, Payment.company_id == company.id) == 0


async def test_a_trade_number_we_never_issued_is_refused(shop, db_session, company, mailbox):
    await _for_sale(db_session, company)
    await _sign_in(shop, mailbox)
    response = await shop.post(
        "/api/payments/payuni/notify", data=_notification("AU000000000000000000")
    )
    assert response.status_code == 400
    assert await _member_until(shop, company) is None


async def test_a_refusal_says_nothing_about_which_check_failed(shop, db_session, company, mailbox):
    """The only reader of this message is somebody guessing at trade numbers."""
    await _for_sale(db_session, company, amount="360")
    await _sign_in(shop, mailbox)
    checkout = (await shop.post("/api/checkout", json={"company": company.slug})).json()

    wrong_amount = await shop.post(
        "/api/payments/payuni/notify", data=_notification(checkout["mer_trade_no"], amount="1")
    )
    no_such_order = await shop.post(
        "/api/payments/payuni/notify", data=_notification("AU000000000000000000")
    )
    assert wrong_amount.text == no_such_order.text
    for body in (wrong_amount.text, no_such_order.text):
        assert checkout["mer_trade_no"] not in body
        assert "360" not in body


async def test_an_unpaid_notification_is_heard_but_buys_nothing(shop, db_session, company, mailbox):
    """An ATM code was issued. PAYUNi has said something true; it is just not a payment."""
    await _for_sale(db_session, company)
    await _sign_in(shop, mailbox)
    checkout = (await shop.post("/api/checkout", json={"company": company.slug})).json()

    response = await shop.post(
        "/api/payments/payuni/notify",
        data=_notification(checkout["mer_trade_no"], trade_status=payuni.TRADE_AWAITING),
    )
    assert response.text == "1|OK"
    assert await _member_until(shop, company) is None

    order = await db_session.get(Order, uuid.UUID(checkout["order_id"]))
    await db_session.refresh(order)
    assert order.state == OrderState.PENDING.value, "still waiting, not failed"


async def test_a_second_year_extends_the_first(shop, db_session, company, mailbox):
    await _for_sale(db_session, company)
    await _sign_in(shop, mailbox)

    first = (await shop.post("/api/checkout", json={"company": company.slug})).json()
    await shop.post("/api/payments/payuni/notify", data=_notification(first["mer_trade_no"]))
    after_one = await _member_until(shop, company)

    second = (await shop.post("/api/checkout", json={"company": company.slug})).json()
    await shop.post("/api/payments/payuni/notify", data=_notification(second["mer_trade_no"]))
    after_two = await _member_until(shop, company)

    assert after_two > after_one
    assert await _count(db_session, Payment, Payment.company_id == company.id) == 2


# --- what is kept, and the notifications that used to fail (P2-B) -------------------------------


async def _events(db_session, mer_trade_no):
    db_session.expire_all()
    return list(
        await db_session.scalars(
            select(PaymentEvent)
            .where(PaymentEvent.mer_trade_no == mer_trade_no)
            .order_by(PaymentEvent.created_at, PaymentEvent.id)
        )
    )


async def _checkout(shop, db_session, company, mailbox, **sale):
    price = await _for_sale(db_session, company, **sale)
    await _sign_in(shop, mailbox)
    checkout = (await shop.post("/api/checkout", json={"company": company.slug})).json()
    return price.id, checkout


async def test_every_notification_is_kept_with_what_became_of_it(
    shop, db_session, company, mailbox
):
    _, checkout = await _checkout(shop, db_session, company, mailbox)
    no = checkout["mer_trade_no"]
    form = _notification(no, trade_no="UNI-KEPT")

    await shop.post("/api/payments/payuni/notify", data=form)
    await shop.post("/api/payments/payuni/notify", data=form)

    first, again = await _events(db_session, no)
    assert (first.outcome, again.outcome) == ("settled", "repeated")
    assert first.payment_id == again.payment_id is not None
    assert first.order_id == uuid.UUID(checkout["order_id"])
    assert first.payload == form, "the form as it was posted, sealed"
    assert first.fields["MerTradeNo"] == no, "and what the envelope said"
    assert (first.external_ref, first.trade_status, first.amount) == ("UNI-KEPT", "1", 360)
    assert first.processed_at is not None and first.error is None
    assert await _count(db_session, Payment, Payment.company_id == company.id) == 1


async def test_a_failure_after_the_payment_is_acknowledged_and_undoes_nothing(
    shop, db_session, company, mailbox
):
    """Was a 500 that PAYUNi would have sent again all day (P2-B inventory, case 1)."""
    _, checkout = await _checkout(shop, db_session, company, mailbox)
    no = checkout["mer_trade_no"]
    await shop.post("/api/payments/payuni/notify", data=_notification(no, trade_no="UNI-1"))
    until = await _member_until(shop, company)

    response = await shop.post(
        "/api/payments/payuni/notify", data=_notification(no, trade_status="2", trade_no="UNI-1")
    )

    assert (response.status_code, response.text) == (200, "1|OK")
    order = await db_session.get(Order, uuid.UUID(checkout["order_id"]))
    await db_session.refresh(order)
    assert order.state == OrderState.PAID.value
    assert await _member_until(shop, company) == until
    assert [e.outcome for e in await _events(db_session, no)] == ["settled", "ignored"]


async def test_a_failure_before_any_payment_marks_the_order_failed(
    shop, db_session, company, mailbox
):
    _, checkout = await _checkout(shop, db_session, company, mailbox)
    no = checkout["mer_trade_no"]
    response = await shop.post(
        "/api/payments/payuni/notify", data=_notification(no, trade_status="2")
    )
    assert response.text == "1|OK"
    order = await db_session.get(Order, uuid.UUID(checkout["order_id"]))
    await db_session.refresh(order)
    assert order.state == OrderState.FAILED.value
    assert [e.outcome for e in await _events(db_session, no)] == ["unpaid"]


async def test_a_price_retired_before_the_notification_still_buys_the_order(
    shop, db_session, company, mailbox
):
    """Was a 500 with the money taken and nothing given (P2-B inventory, case 2)."""
    price_id, checkout = await _checkout(shop, db_session, company, mailbox)
    no = checkout["mer_trade_no"]
    await memberships.retire_price(db_session, await db_session.get(Price, price_id))
    await db_session.commit()

    response = await shop.post("/api/payments/payuni/notify", data=_notification(no))

    assert (response.status_code, response.text) == (200, "1|OK")
    assert await _member_until(shop, company) is not None
    order = await db_session.get(Order, uuid.UUID(checkout["order_id"]))
    await db_session.refresh(order)
    assert order.state == OrderState.PAID.value
    assert [e.outcome for e in await _events(db_session, no)] == ["settled"]
    nothing_new = await shop.post("/api/checkout", json={"company": company.slug})
    assert nothing_new.status_code == 404, "retired: no new order at it"


async def test_an_order_expired_unpaid_is_still_honoured_when_the_money_arrives(
    shop, db_session, company, mailbox
):
    _, checkout = await _checkout(shop, db_session, company, mailbox)
    no = checkout["mer_trade_no"]
    await orders.expire_stale(db_session, now=datetime.now(UTC) + orders.PENDING_FOR * 2)
    await db_session.commit()
    order = await db_session.get(Order, uuid.UUID(checkout["order_id"]))
    await db_session.refresh(order)
    assert order.state == OrderState.EXPIRED.value

    response = await shop.post("/api/payments/payuni/notify", data=_notification(no))

    assert response.text == "1|OK"
    await db_session.refresh(order)
    assert order.state == OrderState.PAID.value
    assert await _member_until(shop, company) is not None


async def test_unreadable_and_refused_notifications_are_kept_too(
    shop, db_session, company, mailbox
):
    _, checkout = await _checkout(shop, db_session, company, mailbox)
    no = checkout["mer_trade_no"]
    forged = _notification(no) | {"HashInfo": "0" * 64}
    wrong = _notification(no, amount="1")

    assert (await shop.post("/api/payments/payuni/notify", data=forged)).status_code == 400
    assert (await shop.post("/api/payments/payuni/notify", data=wrong)).status_code == 400

    db_session.expire_all()
    unreadable = await db_session.scalar(
        select(PaymentEvent).where(PaymentEvent.payload["HashInfo"].astext == "0" * 64)
    )
    assert unreadable.outcome == "unreadable"
    assert unreadable.fields is None and unreadable.mer_trade_no is None
    assert "HashInfo" in unreadable.error
    (refused,) = await _events(db_session, no)
    assert refused.outcome == "refused"
    assert "the notification says 1" in refused.error, "the record says why; the reply does not"
    assert refused.payment_id is None


async def test_a_notification_that_fails_is_kept_with_its_error_and_not_acknowledged(
    shop, db_session, company, mailbox, monkeypatch
):
    _, checkout = await _checkout(shop, db_session, company, mailbox)
    no = checkout["mer_trade_no"]

    async def broken(*args, **kwargs):
        raise RuntimeError("the database went away")

    monkeypatch.setattr(orders, "settle", broken)
    lax = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=shop._transport.app, raise_app_exceptions=False),
        base_url="http://test",
    )
    response = await lax.post("/api/payments/payuni/notify", data=_notification(no))

    assert response.status_code == 500, "not acknowledged: PAYUNi will send it again"
    (event,) = await _events(db_session, no)
    assert event.outcome == "error"
    assert event.error == "RuntimeError: the database went away"
    assert event.fields["MerTradeNo"] == no
    assert await _member_until(shop, company) is None


async def _count(session, model, *where) -> int:
    return await session.scalar(select(func.count()).select_from(model).where(*where))
