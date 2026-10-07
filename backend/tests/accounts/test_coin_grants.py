"""P3-B: the month's coins — who, how many, which month, and once.

The switch (``policy.MONTHLY_GRANTS_ON``) is off in production until P3-C; these tests turn it on
for themselves, and one checks that off means nothing at all.
"""

import ast
import asyncio
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import func, select, text

from autora.accounts import Reader
from autora.accounts.coins import (
    CoinTxn,
    TxnKind,
    balance,
    grant,
    grant_monthly,
    policy,
    reconcile,
    refund,
    spend,
)
from autora.accounts.coins.models import KEY_PATTERN
from autora.accounts.entitlement import Tier
from autora.runtime.actor import Actor

OCTOBER = datetime(2026, 10, 15, 4, 0, tzinfo=UTC)
SYSTEM = Actor.system("grants-test")


@pytest.fixture(autouse=True)
def grants_on(monkeypatch):
    monkeypatch.setattr(policy, "MONTHLY_GRANTS_ON", True)


async def _reader(session) -> uuid.UUID:
    reader = Reader(email=f"g{uuid.uuid4().hex[:12]}@example.com")
    session.add(reader)
    await session.flush()
    return reader.id


async def _txns(session, reader_id) -> int:
    return await session.scalar(
        select(func.count()).select_from(CoinTxn).where(CoinTxn.reader_id == reader_id)
    )


async def proven(session) -> None:
    await session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    await session.execute(text("SET CONSTRAINTS ALL DEFERRED"))


# --- the rules ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("tier", "verified", "gets"),
    [
        (Tier.FREE, True, True),
        (Tier.VIP, True, True),
        (Tier.FREE, False, False),
        (Tier.VIP, False, False),
        (Tier.PUBLIC, True, False),
    ],
)
def test_who_is_eligible(tier, verified, gets):
    assert policy.eligible(tier, verified) is gets


def test_the_numbers_are_d218_s():
    """D-218's monthly amounts; caps of six months' worth (raised from two before any coin was
    given)."""
    assert policy.MONTHLY[Tier.FREE] == policy.MonthlyGrant(amount=50, cap=300)
    assert policy.MONTHLY[Tier.VIP] == policy.MonthlyGrant(amount=500, cap=3000)
    assert policy.POLICY_VERSION == "p3b-2"


def test_grants_are_off_until_p3c():
    """The value as shipped, read from the source: the fixture above turns it on for these
    tests only."""
    source = ast.parse(Path(policy.__file__).read_text())
    shipped = {
        node.targets[0].id: node.value.value
        for node in source.body
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant)
    }
    assert shipped["MONTHLY_GRANTS_ON"] is False


@pytest.mark.parametrize(
    ("utc", "month"),
    [
        (datetime(2026, 10, 31, 15, 59, tzinfo=UTC), "2026-10"),  # 23:59 on the 31st in Taipei
        (datetime(2026, 10, 31, 16, 0, tzinfo=UTC), "2026-11"),  # 00:00 on 1 November in Taipei
        (datetime(2026, 12, 31, 16, 0, tzinfo=UTC), "2027-01"),
    ],
)
def test_a_month_starts_at_midnight_in_taipei(utc, month):
    assert policy.month_of(utc) == month


def test_the_key_is_one_the_ledger_accepts():
    reader = uuid.uuid4()
    key = policy.grant_key(Tier.VIP, reader, "2026-10")
    assert key == f"grant:vip:{reader}:2026-10"
    assert re.fullmatch(KEY_PATTERN.strip("^$"), key)


# --- granting -----------------------------------------------------------------------------------


async def test_the_first_time_this_month_gives_the_tier_s_coins_and_says_why(db_session):
    reader = await _reader(db_session)
    posted = await grant_monthly(
        db_session, reader, tier=Tier.FREE, email_verified=True, now=OCTOBER
    )
    assert posted is not None and posted.created
    txn = posted.txn
    assert (txn.kind, txn.amount, txn.requested, txn.cap) == ("MONTHLY_GRANT", 50, 50, 300)
    assert txn.idempotency_key == f"grant:free:{reader}:2026-10"
    assert txn.meta == {
        "tier": "free",
        "month": "2026-10",
        "policy": "p3b-2",
        "monthly": 50,
        "cap": 300,
        "trigger": "auth_me",
    }
    assert txn.actor == {"kind": "system", "id": "monthly-grant"}
    await proven(db_session)


async def test_the_rest_of_the_month_writes_nothing(db_session):
    reader = await _reader(db_session)
    await grant_monthly(db_session, reader, tier=Tier.FREE, email_verified=True, now=OCTOBER)
    for _ in range(3):
        again = await grant_monthly(
            db_session, reader, tier=Tier.FREE, email_verified=True, now=OCTOBER
        )
        assert again is None
    assert await _txns(db_session, reader) == 1
    november = datetime(2026, 11, 2, tzinfo=UTC)
    nxt = await grant_monthly(db_session, reader, tier=Tier.FREE, email_verified=True, now=november)
    assert nxt is not None and nxt.txn.meta["month"] == "2026-11"
    await proven(db_session)


async def test_an_unproven_address_gets_nothing_until_it_is_proven(db_session):
    reader = await _reader(db_session)
    assert (
        await grant_monthly(db_session, reader, tier=Tier.FREE, email_verified=False, now=OCTOBER)
        is None
    )
    assert await _txns(db_session, reader) == 0
    later = await grant_monthly(
        db_session, reader, tier=Tier.FREE, email_verified=True, now=OCTOBER
    )
    assert later is not None and later.txn.amount == 50


async def test_free_then_vip_in_one_month_is_50_then_550(db_session):
    reader = await _reader(db_session)
    await grant_monthly(db_session, reader, tier=Tier.FREE, email_verified=True, now=OCTOBER)
    vip = await grant_monthly(db_session, reader, tier=Tier.VIP, email_verified=True, now=OCTOBER)
    assert vip.txn.amount == 500 and await balance(db_session, reader) == 550
    # VIP, then FREE, then VIP again in the same month: no second VIP grant
    free_again = await grant_monthly(
        db_session, reader, tier=Tier.FREE, email_verified=True, now=OCTOBER
    )
    assert free_again is None  # FREE's month was given already
    assert (
        await grant_monthly(db_session, reader, tier=Tier.VIP, email_verified=True, now=OCTOBER)
        is None
    )
    assert await balance(db_session, reader) == 550
    await proven(db_session)


async def test_a_downgraded_reader_s_month_is_zero_and_written(db_session):
    reader = await _reader(db_session)
    await grant(
        db_session, reader, requested=850, cap=850, kind=TxnKind.PROMOTION_GRANT,
        idempotency_key=f"promo:setup:{reader}", actor=SYSTEM,
    )  # fmt: skip
    free = await grant_monthly(db_session, reader, tier=Tier.FREE, email_verified=True, now=OCTOBER)
    assert (free.txn.amount, free.txn.balance_after) == (0, 850)
    assert await grant_monthly(
        db_session, reader, tier=Tier.FREE, email_verified=True, now=OCTOBER
    ) is None  # fmt: skip
    await proven(db_session)


async def test_after_a_refund_past_the_cap_the_month_is_zero(db_session):
    reader = await _reader(db_session)
    await grant(
        db_session, reader, requested=3000, cap=3000, kind=TxnKind.PROMOTION_GRANT,
        idempotency_key=f"promo:setup:{reader}", actor=SYSTEM,
    )  # fmt: skip
    spent = await spend(
        db_session, reader, amount=5, idempotency_key=f"spend:x:{reader}", actor=SYSTEM
    )
    await grant(
        db_session, reader, requested=5, cap=3000, kind=TxnKind.PROMOTION_GRANT,
        idempotency_key=f"promo:refill:{reader}", actor=SYSTEM,
    )  # fmt: skip
    await refund(db_session, spent.txn.id, actor=SYSTEM)
    vip = await grant_monthly(db_session, reader, tier=Tier.VIP, email_verified=True, now=OCTOBER)
    assert (vip.txn.amount, vip.txn.balance_after) == (0, 3005)
    await proven(db_session)


async def test_off_means_nothing_at_all(db_session, monkeypatch):
    monkeypatch.setattr(policy, "MONTHLY_GRANTS_ON", False)
    reader = await _reader(db_session)
    assert (
        await grant_monthly(db_session, reader, tier=Tier.VIP, email_verified=True, now=OCTOBER)
        is None
    )
    assert await _txns(db_session, reader) == 0


# --- many at once, with real commits -------------------------------------------------------------


async def test_twenty_at_once_grant_once(committed):
    async with committed() as session:
        reader = Reader(email=f"g{uuid.uuid4().hex[:12]}@example.com")
        session.add(reader)
        await session.commit()
        reader_id = reader.id

    async def one() -> bool:
        async with committed() as session:
            posted = await grant_monthly(
                session, reader_id, tier=Tier.VIP, email_verified=True, now=OCTOBER
            )
            await session.commit()
            return bool(posted and posted.created)

    created = await asyncio.gather(*(one() for _ in range(20)))
    assert created.count(True) == 1
    async with committed() as session:
        assert await balance(session, reader_id) == 500
        assert await _txns(session, reader_id) == 1
        report = await reconcile(session)
    assert report.ok, report.problems
