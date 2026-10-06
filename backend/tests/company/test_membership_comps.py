"""D-228 (P2): VIP given by an admin for internal testing — a comp.

A comp is its own path, never a purchase: no order, no payment, no ledger row, no revenue, and
its customer is ``comp``, never counted as paying. Every comp is a ``membership_grants`` row;
ending one early revokes it — the row keeps who, when and why — and access falls back to
whatever else is still running. Access is the membership's dates, as it always was.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from autora.company import customers, memberships
from autora.company.memberships import MembershipError
from autora.company.organization import add_business_unit, add_product
from autora.company.revenue import membership_numbers
from autora.db.models import (
    BusinessUnitState,
    Customer,
    CustomerKind,
    GrantSource,
    Membership,
    MembershipGrant,
    MembershipState,
    Order,
    Payment,
    PriceInterval,
    ProductState,
    Transaction,
)
from autora.runtime.actor import Actor
from tests.conftest import unique_company

ADMIN = Actor.human("admin:0190e5a0-0000-7000-8000-000000000001")
OTHER_ADMIN = Actor.human("admin:0190e5a0-0000-7000-8000-000000000002")
PAYUNI = Actor.system("payments:payuni")
NOW = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)
READER = "reader:0190e5a0-0000-7000-8000-0000000000aa"


async def _world(session):
    company = await unique_company(session, "comps")
    unit = await add_business_unit(
        session, company_id=company.id, key="ai_media", name="AI Media",
        actor=ADMIN, state=BusinessUnitState.ACTIVE,
    )  # fmt: skip
    product = await add_product(
        session, company_id=company.id, key=memberships.PRODUCT_KEY, name="Membership",
        business_unit_id=unit.id, actor=ADMIN, state=ProductState.LIVE,
    )  # fmt: skip
    return company, product


async def _comp(session, product, *, until=NOW + timedelta(days=30), reader=READER, **kwargs):
    return await memberships.grant_comp(
        session, product, customer_ref=reader, until=until,
        reason=kwargs.pop("reason", "internal test account"), actor=kwargs.pop("actor", ADMIN),
        now=kwargs.pop("now", NOW),
    )  # fmt: skip


async def _until(session, company, *, at=NOW, reader=READER):
    return await memberships.access_until(
        session, company_id=company.id, customer_ref=reader, at=at
    )


async def _count(session, model, company):
    return await session.scalar(
        select(func.count()).select_from(model).where(model.company_id == company.id)
    )


async def test_a_comp_gives_access_until_the_day_it_says(db_session):
    company, product = await _world(db_session)
    until = NOW + timedelta(days=30)

    grant = await _comp(db_session, product, until=until)

    assert await _until(db_session, company) == until
    assert grant.source == GrantSource.ADMIN_COMP and grant.payment_id is None
    assert (grant.started_at, grant.expires_at) == (NOW, until)
    assert grant.reason == "internal test account"
    assert grant.actor == {"kind": "human", "id": ADMIN.id}
    assert grant.revoked_at is None


async def test_a_comp_sells_nothing(db_session):
    """No order, no payment, no ledger row, no revenue — not even zero-priced ones."""
    company, product = await _world(db_session)
    await _comp(db_session, product)

    assert await _count(db_session, Order, company) == 0
    assert await _count(db_session, Payment, company) == 0
    assert await _count(db_session, Transaction, company) == 0
    numbers = await membership_numbers(
        db_session, company.id, since=NOW - timedelta(days=1), until=NOW + timedelta(days=1)
    )
    assert numbers.payments == 0 and numbers.membership_revenue == Decimal(0)
    assert numbers.new_members == 0


async def test_a_comp_customer_is_not_a_paying_customer(db_session):
    company, product = await _world(db_session)
    await _comp(db_session, product)

    customer = await customers.by_external_ref(db_session, company.id, READER)
    assert customer.kind == CustomerKind.COMP
    assert await customers.paying(db_session, company.id, at=NOW) == 0


async def test_a_paying_customer_given_a_comp_stays_paying(db_session):
    company, product = await _world(db_session)
    price = await memberships.add_price(
        db_session, product, amount=Decimal("30"), interval=PriceInterval.MONTH
    )
    await memberships.purchase(
        db_session, price=price, customer_ref=READER, provider="payuni",
        external_ref="T-paid-1", actor=PAYUNI, paid_at=NOW,
    )  # fmt: skip

    await _comp(db_session, product, until=NOW + timedelta(days=90))

    customer = await customers.by_external_ref(db_session, company.id, READER)
    assert customer.kind == CustomerKind.SUBSCRIBER
    assert await customers.paying(db_session, company.id, at=NOW) == 1
    assert await _count(db_session, Payment, company) == 1, "the comp added no payment"


async def test_access_ends_when_the_comp_runs_out(db_session):
    company, product = await _world(db_session)
    until = NOW + timedelta(days=7)
    await _comp(db_session, product, until=until)

    assert await _until(db_session, company, at=until - timedelta(seconds=1)) == until
    assert await _until(db_session, company, at=until) is None


async def test_revoking_ends_access_and_keeps_the_history(db_session):
    company, product = await _world(db_session)
    grant = await _comp(db_session, product)
    later = NOW + timedelta(days=2)

    revoked = await memberships.revoke_grant(
        db_session, grant.id, reason="test finished", actor=OTHER_ADMIN, now=later
    )

    assert await _until(db_session, company, at=later) is None
    assert revoked.id == grant.id
    assert (revoked.revoked_at, revoked.revoke_reason) == (later, "test finished")
    assert revoked.revoked_by == {"kind": "human", "id": OTHER_ADMIN.id}
    assert (revoked.reason, revoked.expires_at) == ("internal test account", grant.expires_at), (
        "what was given is still on the row"
    )
    assert await _count(db_session, MembershipGrant, company) == 1, "nothing was deleted"


async def test_a_comp_is_revoked_once_and_only_with_a_reason(db_session):
    _, product = await _world(db_session)
    grant = await _comp(db_session, product)

    with pytest.raises(MembershipError, match="needs a reason"):
        await memberships.revoke_grant(db_session, grant.id, reason="  ", actor=ADMIN, now=NOW)
    await memberships.revoke_grant(db_session, grant.id, reason="done", actor=ADMIN, now=NOW)
    with pytest.raises(MembershipError, match="already revoked"):
        await memberships.revoke_grant(db_session, grant.id, reason="again", actor=ADMIN, now=NOW)


async def test_revoking_in_the_same_instant_it_was_given_keeps_the_table_s_rules(db_session):
    """The membership must end after it started (``expires_at > started_at``), even when the
    comp that began it is revoked at that very moment."""
    company, product = await _world(db_session)
    grant = await _comp(db_session, product)

    await memberships.revoke_grant(db_session, grant.id, reason="mistake", actor=ADMIN, now=NOW)

    membership = await db_session.get(Membership, grant.membership_id)
    assert membership.expires_at > membership.started_at
    assert await _until(db_session, company, at=NOW + timedelta(seconds=1)) is None


async def test_revoking_a_comp_falls_back_to_what_was_paid(db_session):
    company, product = await _world(db_session)
    price = await memberships.add_price(
        db_session, product, amount=Decimal("30"), interval=PriceInterval.MONTH
    )
    payment, _ = await memberships.purchase(
        db_session, price=price, customer_ref=READER, provider="payuni",
        external_ref="T-paid-2", actor=PAYUNI, paid_at=NOW,
    )  # fmt: skip
    grant = await _comp(db_session, product, until=NOW + timedelta(days=120))
    assert await _until(db_session, company) == NOW + timedelta(days=120)

    await memberships.revoke_grant(db_session, grant.id, reason="done", actor=ADMIN, now=NOW)

    assert await _until(db_session, company) == payment.grants_until


async def test_two_comps_run_to_the_later_and_revoking_one_keeps_the_other(db_session):
    company, product = await _world(db_session)
    short = await _comp(db_session, product, until=NOW + timedelta(days=10))
    long = await _comp(db_session, product, until=NOW + timedelta(days=40))
    assert await _until(db_session, company) == long.expires_at

    await memberships.revoke_grant(db_session, long.id, reason="done", actor=ADMIN, now=NOW)
    assert await _until(db_session, company) == short.expires_at
    assert short.membership_id == long.membership_id, "one membership, two grants"


async def test_a_lapsed_membership_comes_back_with_a_comp(db_session):
    company, product = await _world(db_session)
    first = await _comp(db_session, product, until=NOW + timedelta(days=1))
    membership = await db_session.get(Membership, first.membership_id)
    membership.state = MembershipState.EXPIRED.value
    later = NOW + timedelta(days=10)

    await _comp(db_session, product, until=later + timedelta(days=5), now=later)

    assert membership.state == MembershipState.ACTIVE
    assert membership.started_at == later
    assert await _until(db_session, company, at=later) == later + timedelta(days=5)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"reason": "   "}, "needs a reason"),
        ({"reason": "x" * 501}, "at most"),
        ({"until": NOW}, "in the future"),
        ({"until": NOW - timedelta(days=1)}, "in the future"),
    ],
)
async def test_what_is_not_a_comp(db_session, change, message):
    company, product = await _world(db_session)
    with pytest.raises(MembershipError, match=message):
        await _comp(db_session, product, **change)
    assert await _count(db_session, Customer, company) == 0


async def test_the_comps_list_shows_running_ones_or_all(db_session):
    company, product = await _world(db_session)
    kept = await _comp(db_session, product, reader="reader:0190e5a0-0000-7000-8000-0000000000b1")
    ended = await _comp(db_session, product, reader="reader:0190e5a0-0000-7000-8000-0000000000b2")
    await memberships.revoke_grant(db_session, ended.id, reason="done", actor=ADMIN, now=NOW)

    everything = await memberships.comp_grants(db_session, company.id)
    running = await memberships.comp_grants(db_session, company.id, running_at=NOW)

    assert {grant.id for grant, _ in everything} == {kept.id, ended.id}
    assert [grant.id for grant, _ in running] == [kept.id]
    assert dict((grant.id, ref) for grant, ref in everything)[kept.id].endswith("b1")
