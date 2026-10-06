"""Buying a month or a year of membership, and hearing back that it was paid for (T-702, D-024).

- GET  /api/checkout/offer[?interval=month|year&company=<slug>] -> what it costs, or nothing
- POST /api/checkout                        -> an order, and the form that opens PAYUNi's page
- POST /api/payments/payuni/notify          -> PAYUNi telling us the money arrived (kept first,
                                               in ``payment_events``)

The first two belong to the reader's browser and go by the session cookie, like the rest of the
public site. The third belongs to PAYUNi's servers and goes by the shared secret: it carries no
cookie, and it is the only one of the three that grants anything. A browser coming back from the
payment page is told nothing it did not already know — the return page asks ``/api/auth/me``
again, and the answer is whatever the notification has made true by then.

**Closed in P2** (D-228, D-231): the catalogue keeps what PayUni was applied with (D-161: NT$30
a month), but nothing is sold until P8 opens payments. The offer says what it costs and
``available: false``; checkout is refused
before anything else — before the sign-in, before the shop's keys, before any order — whatever
``SITE_MEMBERSHIP_OPEN`` says and whether or not the shop is configured
(``accounts.entitlement.CHECKOUT_OPEN``). VIP is given for testing instead (admin_comp).

Refusals are deliberately dull. A notification that does not add up gets 400 and a sentence with
nothing in it, because the only reader of that sentence is somebody guessing at trade numbers.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Annotated, Literal
from urllib.parse import parse_qsl

from fastapi import APIRouter, Cookie, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from autora.accounts import SESSION_COOKIE, customer_ref, entitlement, reader_for
from autora.company import memberships, orders, payment_events
from autora.db.models import Company, Price, PriceInterval
from autora.db.models import PaymentEventOutcome as Outcome
from autora.infra.payments import payuni
from autora.infra.settings import Settings
from autora.runtime.actor import Actor
from autora_api.deps import Session, settings_dep

router = APIRouter(tags=["payments"])

PROVIDER = "payuni"

SessionCookie = Annotated[str | None, Cookie(alias=SESSION_COOKIE)]
SettingsDep = Annotated[Settings, Depends(settings_dep)]
CompanySlug = Annotated[str | None, Query(max_length=100)]
Interval = Literal["month", "year"]

PRODUCT_DESCRIPTIONS = {"month": "艾矽鯨會員一個月", "year": "艾矽鯨會員一年"}
"""What PAYUNi's page and the buyer's receipt call it, by what one payment buys (D-034)."""


class Offer(BaseModel):
    """What is for sale, for a page that has to name a price before anybody clicks."""

    amount: Decimal
    currency: str
    interval: str
    available: bool = True
    """Whether it can be bought now. False in P2 for every price (D-231): the amount is still
    the catalogue's, so the page can say what it will cost."""


class CheckoutRequest(BaseModel):
    company: str | None = Field(default=None, max_length=100)
    interval: Interval = "year"
    lang: str = Field(default="zh-TW", pattern=r"^[a-z]{2}(-[A-Z][A-Za-z]{1,3})?$")


class Checkout(BaseModel):
    """Everything the browser needs to hand the reader over to PAYUNi, and nothing secret."""

    order_id: uuid.UUID
    mer_trade_no: str
    amount: Decimal
    currency: str
    url: str
    fields: dict[str, str]


async def _company_id(session, slug: str | None) -> uuid.UUID | None:
    query = select(Company.id) if slug is None else select(Company.id).where(Company.slug == slug)
    return await session.scalar(query.order_by(Company.created_at).limit(1))


def _secrets(settings: Settings) -> tuple[str, str, str]:
    """The shop's three ids, or 503. A site with no store cannot take money, and saying so
    plainly beats sending somebody to a payment page that will not open."""
    mer_id = settings.payuni_mer_id
    key = settings.payuni_hash_key
    iv = settings.payuni_hash_iv
    if not (mer_id and key and iv):
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "payments are not configured on this site"
        )
    return mer_id, key.get_secret_value(), iv.get_secret_value()


@router.get("/api/checkout/offer")
async def get_offer(
    session: Session, company: CompanySlug = None, interval: Interval = "year"
) -> Offer:
    """What a month or a year costs here. ``available`` is false when that one is not for sale
    yet, which is a fact about the site rather than an error — the page says "soon" instead of a
    price."""
    company_id = await _company_id(session, company)
    price = (
        None
        if company_id is None
        else await memberships.offer(session, company_id, interval=PriceInterval(interval))
    )
    if price is None:
        return Offer(amount=Decimal(0), currency="TWD", interval=interval, available=False)
    return Offer(
        amount=price.amount,
        currency=price.currency,
        interval=price.interval,
        available=entitlement.CHECKOUT_OPEN,
    )


@router.post("/api/checkout", status_code=status.HTTP_201_CREATED)
async def start_checkout(
    body: CheckoutRequest,
    session: Session,
    settings: SettingsDep,
    autora_reader: SessionCookie = None,
) -> Checkout:
    """Open an order and build the form that opens PAYUNi's page.

    Signing in comes first: the order records who a year is for, and a reader id is the only
    name this layer has for anybody (D-018). Nothing is granted here — the order is PENDING
    until PAYUNi says otherwise, even if the reader never comes back.

    Closed in P2 (D-231): refused first, so no order is ever opened, at any price.
    """
    if not entitlement.CHECKOUT_OPEN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "membership is not on sale yet")
    reader = await reader_for(session, autora_reader)
    if reader is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "sign in before buying a membership")
    mer_id, key, iv = _secrets(settings)
    company_id = await _company_id(session, body.company)
    price = (
        None
        if company_id is None
        else await memberships.offer(session, company_id, interval=PriceInterval(body.interval))
    )
    if price is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "nothing is for sale here yet")

    order = await orders.open_order(
        session,
        price=price,
        customer_ref=customer_ref(reader.id),
        provider=PROVIDER,
    )
    try:
        page = payuni.payment_page(
            base_url=settings.payuni_base_url,
            mer_id=mer_id,
            key=key,
            iv=iv,
            mer_trade_no=order.mer_trade_no,
            amount=order.amount,
            description=PRODUCT_DESCRIPTIONS[body.interval],
            return_url=settings.payuni_return_url,
            notify_url=settings.payuni_notify_url,
            email=reader.email,
            lang="en" if body.lang.startswith("en") else "zh-tw",
        )
    except (payuni.Unsupported, payuni.EnvelopeError) as exc:
        # a misconfigured shop or an impossible price: no order, and a 503 rather than a 500
        await session.rollback()
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    await session.commit()
    return Checkout(
        order_id=order.id,
        mer_trade_no=order.mer_trade_no,
        amount=order.amount,
        currency=order.currency,
        url=page.url,
        fields=page.fields,
    )


@router.post("/api/payments/payuni/notify")
async def payuni_notify(request: Request, session: Session, settings: SettingsDep) -> Response:
    """PAYUNi, server to server: this order was paid. The only thing that grants a year.

    Every notification is written down first (``payment_events``, committed on its own), then
    opened and dealt with, and the record says how that went (P2-B).

    Answers ``1|OK`` once it has been dealt with — including a notification that is heard but
    changes nothing: a repeat, an ATM code, a "failed" for an order already paid. Answers 400
    when it is not PAYUNi's or does not add up, and 500 when dealing with it failed, because
    PAYUNi keeps sending a notification nobody acknowledged — which is what we want when the
    database was briefly unreachable, and harmless when the message was never PAYUNi's.
    """
    _, key, iv = _secrets(settings)
    # PAYUNi posts application/x-www-form-urlencoded, which is a query string in the body. Reading
    # it directly keeps the one endpoint that strangers can reach off the multipart parser.
    body = await request.body()
    form = dict(parse_qsl(body.decode("utf-8", "replace"), keep_blank_values=True))
    event_id = await payment_events.receive(
        session, provider=PROVIDER, payload=payment_events.payload_of(body, form)
    )
    await session.commit()

    try:
        notification = payuni.read_notification(form, key=key, iv=iv)
    except payuni.EnvelopeError as exc:
        await payment_events.record(session, event_id, Outcome.UNREADABLE, error=str(exc))
        await session.commit()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "unreadable") from None
    envelope = payment_events.opened(
        fields=notification.fields,
        mer_trade_no=notification.mer_trade_no,
        external_ref=notification.trade_no,
        trade_status=notification.trade_status,
        amount=notification.trade_amt,
    )

    try:
        outcome, order_id, payment_id = await _deal_with(session, notification)
    except orders.NotificationRefused as exc:
        await session.rollback()
        await payment_events.record(session, event_id, Outcome.REFUSED, error=str(exc), **envelope)
        await session.commit()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "refused") from None
    except Exception as exc:
        await session.rollback()
        await payment_events.record(
            session, event_id, Outcome.ERROR, error=f"{type(exc).__name__}: {exc}", **envelope
        )
        await session.commit()
        raise
    # in the same transaction as what it did: the record never says settled when nothing was
    await payment_events.record(
        session, event_id, outcome, order_id=order_id, payment_id=payment_id, **envelope
    )
    await session.commit()
    return Response(payuni.acknowledge(), media_type="text/plain")


async def _deal_with(
    session, notification: payuni.Notification
) -> tuple[Outcome, uuid.UUID | None, uuid.UUID | None]:
    """Act on an opened notification. Does not commit. Raises ``NotificationRefused``."""
    if not notification.paid:
        # nothing is granted, but this is PAYUNi's message and it has been heard: acknowledge it,
        # or it will be sent again all day. An ATM code was issued, or a card was declined.
        order, _ = await orders.hear_unpaid(
            session,
            provider=PROVIDER,
            mer_trade_no=notification.mer_trade_no,
            waiting=notification.trade_status == payuni.TRADE_AWAITING,
        )
        if order is not None and order.state == orders.OrderState.PAID.value:
            return Outcome.IGNORED, order.id, order.payment_id
        return Outcome.UNPAID, order.id if order is not None else None, None

    settled = await orders.settle(
        session,
        provider=PROVIDER,
        mer_trade_no=notification.mer_trade_no,
        external_ref=notification.trade_no or notification.mer_trade_no,
        amount=notification.trade_amt,
        actor=Actor.system("payments"),
    )
    outcome = Outcome.SETTLED if settled.granted else Outcome.REPEATED
    return outcome, settled.order.id, settled.payment.id


__all__ = ["Checkout", "Offer", "Price", "router"]
