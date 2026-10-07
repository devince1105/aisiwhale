"""P3-A: the Whale Coin ledger core — what each movement writes, and what it refuses.

Inside one rolled-back transaction per test, so the commit-time checks never run on their own:
``proven`` runs them (``SET CONSTRAINTS ALL IMMEDIATE``) at the point a test says the ledger
must already add up. The races, with real commits, are in ``test_coin_races``.
"""

import uuid

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError

from autora.accounts import Reader
from autora.accounts.coins import (
    CapExceeded,
    CoinEntry,
    CoinError,
    CoinTxn,
    CoinWallet,
    IdempotencyConflict,
    InsufficientCoins,
    NotRefundable,
    TxnKind,
    adjust,
    balance,
    grant,
    reconcile,
    refund,
    spend,
)
from autora.runtime.actor import Actor

SYSTEM = Actor.system("coins-test")
ADMIN = Actor.human("admin:test")


async def _reader(session) -> uuid.UUID:
    reader = Reader(email=f"r{uuid.uuid4().hex[:12]}@example.com")
    session.add(reader)
    await session.flush()
    return reader.id


async def proven(session) -> None:
    """Run the commit-time checks now, then let later statements defer again."""
    await session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    await session.execute(text("SET CONSTRAINTS ALL DEFERRED"))


async def _fill(session, reader_id, coins: int) -> None:
    """Start a reader at ``coins``, by a promotion nobody capped below it."""
    if coins:
        await grant(
            session, reader_id, requested=coins, cap=coins, kind=TxnKind.PROMOTION_GRANT,
            idempotency_key=f"promo:setup:{reader_id}", actor=SYSTEM,
        )  # fmt: skip


def _month_key(tier: str, reader_id, month: str = "2026-10") -> str:
    return f"grant:{tier}:{reader_id}:{month}"


async def _count(session, model, *where) -> int:
    return await session.scalar(select(func.count()).select_from(model).where(*where))


# --- granting: never past the cap ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("held", "cap", "given", "after"),
    [
        (849, 1000, 151, 1000),
        (850, 1000, 150, 1000),
        (1000, 1000, 0, 1000),
        (500, 1000, 500, 1000),
        (0, 1000, 500, 500),
        (99, 100, 1, 100),
        (0, 100, 50, 50),
    ],
)
async def test_a_grant_stops_at_the_cap(db_session, held, cap, given, after):
    reader = await _reader(db_session)
    await _fill(db_session, reader, held)
    requested = 500 if cap == 1000 else 50
    posted = await grant(
        db_session, reader, requested=requested, cap=cap,
        idempotency_key=_month_key("vip" if cap == 1000 else "free", reader), actor=SYSTEM,
    )  # fmt: skip
    assert posted.created is True
    assert (posted.txn.amount, posted.txn.balance_after) == (given, after)
    assert (posted.txn.requested, posted.txn.cap) == (requested, cap)
    assert await balance(db_session, reader) == after
    await proven(db_session)


async def test_a_grant_capped_to_nothing_is_written_and_spends_its_month(db_session):
    """Q1: the month was given, as nothing; spending below the cap does not bring it back."""
    reader = await _reader(db_session)
    await _fill(db_session, reader, 1000)
    key = _month_key("vip", reader)
    first = await grant(
        db_session, reader, requested=500, cap=1000, idempotency_key=key, actor=SYSTEM
    )
    assert (first.txn.amount, first.created) == (0, True)
    assert await _count(db_session, CoinEntry, CoinEntry.txn_id == first.txn.id) == 0

    await spend(db_session, reader, amount=600, idempotency_key=f"spend:t:{reader}", actor=SYSTEM)
    again = await grant(
        db_session, reader, requested=500, cap=1000, idempotency_key=key, actor=SYSTEM
    )
    assert (again.created, again.txn.id) == (False, first.txn.id)
    assert await balance(db_session, reader) == 400
    nxt = await grant(
        db_session, reader, requested=500, cap=1000,
        idempotency_key=_month_key("vip", reader, "2026-11"), actor=SYSTEM,
    )  # fmt: skip
    assert nxt.txn.amount == 500, "next month is a new grant"
    await proven(db_session)


async def test_a_downgraded_reader_keeps_what_they_hold(db_session):
    """D-219: VIP to FREE takes nothing back; FREE's grant is nothing while above FREE's cap."""
    reader = await _reader(db_session)
    await _fill(db_session, reader, 850)
    free = await grant(
        db_session, reader, requested=50, cap=100, idempotency_key=_month_key("free", reader),
        actor=SYSTEM,
    )  # fmt: skip
    assert free.txn.amount == 0
    assert await balance(db_session, reader) == 850
    await proven(db_session)


async def test_free_then_vip_in_one_month_gets_both_never_past_the_vip_cap(db_session):
    reader = await _reader(db_session)
    free = await grant(
        db_session, reader, requested=50, cap=100, idempotency_key=_month_key("free", reader),
        actor=SYSTEM,
    )  # fmt: skip
    vip = await grant(
        db_session, reader, requested=500, cap=1000, idempotency_key=_month_key("vip", reader),
        actor=SYSTEM,
    )  # fmt: skip
    assert (free.txn.amount, vip.txn.amount, await balance(db_session, reader)) == (50, 500, 550)
    again = await grant(
        db_session, reader, requested=500, cap=1000, idempotency_key=_month_key("vip", reader),
        actor=SYSTEM,
    )  # fmt: skip
    assert again.created is False and await balance(db_session, reader) == 550

    other = await _reader(db_session)
    await _fill(db_session, other, 600)
    topped = await grant(
        db_session, other, requested=500, cap=1000, idempotency_key=_month_key("vip", other),
        actor=SYSTEM,
    )  # fmt: skip
    assert (topped.txn.amount, await balance(db_session, other)) == (400, 1000)
    await proven(db_session)


async def test_only_grants_are_granted(db_session):
    reader = await _reader(db_session)
    with pytest.raises(CoinError):
        await grant(
            db_session, reader, requested=5, cap=10, kind=TxnKind.SPEND,
            idempotency_key=f"spend:x:{reader}", actor=SYSTEM,
        )  # fmt: skip


# --- spending and refunds -----------------------------------------------------------------------


async def test_a_spend_the_balance_cannot_cover_writes_nothing(db_session):
    reader = await _reader(db_session)
    await _fill(db_session, reader, 4)
    before = await _count(db_session, CoinTxn, CoinTxn.reader_id == reader)
    with pytest.raises(InsufficientCoins):
        await spend(db_session, reader, amount=5, idempotency_key=f"spend:a:{reader}", actor=SYSTEM)
    assert await _count(db_session, CoinTxn, CoinTxn.reader_id == reader) == before
    assert await balance(db_session, reader) == 4
    exact = await spend(
        db_session, reader, amount=4, idempotency_key=f"spend:b:{reader}", actor=SYSTEM
    )
    assert (exact.txn.amount, exact.txn.balance_after) == (-4, 0)
    await proven(db_session)


async def test_a_refund_gives_back_the_whole_spend_even_past_the_cap(db_session):
    """D-220: refunds are not grants."""
    reader = await _reader(db_session)
    await _fill(db_session, reader, 1000)
    spent = await spend(
        db_session, reader, amount=5, idempotency_key=f"spend:article:{reader}:a1", actor=SYSTEM,
        ref_type="article", ref_id="a1",
    )  # fmt: skip
    await grant(
        db_session, reader, requested=500, cap=1000, idempotency_key=_month_key("vip", reader),
        actor=SYSTEM,
    )  # fmt: skip
    assert await balance(db_session, reader) == 1000

    back = await refund(db_session, spent.txn.id, actor=SYSTEM)
    assert (back.txn.amount, back.txn.balance_after, back.txn.cap) == (5, 1005, None)
    assert back.txn.reverses_txn_id == spent.txn.id
    assert back.txn.idempotency_key == f"refund:{spent.txn.id}"
    assert (back.txn.ref_type, back.txn.ref_id) == ("article", "a1")
    await proven(db_session)


async def test_after_a_refund_past_the_cap_the_month_s_grant_is_zero_and_written(db_session):
    """The cap stops a movement from raising the balance past it, not a balance already above it
    (D-220): the month's grant is 0, written, and the key is spent."""
    reader = await _reader(db_session)
    await _fill(db_session, reader, 1000)
    spent = await spend(
        db_session, reader, amount=5, idempotency_key=f"spend:h:{reader}", actor=SYSTEM
    )
    await adjust(
        db_session, reader, amount=5, cap=1000, reason="back to the cap",
        idempotency_key=f"adj:{uuid.uuid4().hex}", actor=ADMIN,
    )  # fmt: skip
    await refund(db_session, spent.txn.id, actor=SYSTEM)
    assert await balance(db_session, reader) == 1005

    zero = await grant(
        db_session, reader, requested=500, cap=1000, idempotency_key=_month_key("vip", reader),
        actor=SYSTEM,
    )  # fmt: skip
    assert (zero.created, zero.txn.amount, zero.txn.balance_after, zero.txn.cap) == (
        True,
        0,
        1005,
        1000,
    )
    assert await _count(db_session, CoinEntry, CoinEntry.txn_id == zero.txn.id) == 0
    free = await grant(
        db_session, reader, requested=50, cap=100, idempotency_key=_month_key("free", reader),
        actor=SYSTEM,
    )  # fmt: skip
    assert (free.txn.amount, free.txn.balance_after) == (0, 1005)
    with pytest.raises(CapExceeded):
        await adjust(
            db_session, reader, amount=1, cap=1000, reason="over",
            idempotency_key=f"adj:{uuid.uuid4().hex}", actor=ADMIN,
        )  # fmt: skip
    await proven(db_session)


async def test_a_spend_is_refunded_once(db_session):
    reader = await _reader(db_session)
    await _fill(db_session, reader, 10)
    spent = await spend(
        db_session, reader, amount=5, idempotency_key=f"spend:c:{reader}", actor=SYSTEM
    )
    first = await refund(db_session, spent.txn.id, actor=SYSTEM)
    again = await refund(db_session, spent.txn.id, actor=SYSTEM)
    assert (again.created, again.txn.id) == (False, first.txn.id)
    assert await balance(db_session, reader) == 10
    with pytest.raises(NotRefundable):
        await refund(db_session, first.txn.id, actor=SYSTEM)  # a refund is not a spend
    await proven(db_session)


async def test_a_grant_cannot_be_refunded(db_session):
    reader = await _reader(db_session)
    granted = await grant(
        db_session, reader, requested=50, cap=100, idempotency_key=_month_key("free", reader),
        actor=SYSTEM,
    )  # fmt: skip
    with pytest.raises(NotRefundable):
        await refund(db_session, granted.txn.id, actor=SYSTEM)
    with pytest.raises(NotRefundable):
        await refund(db_session, uuid.uuid4(), actor=SYSTEM)


# --- idempotency --------------------------------------------------------------------------------


async def test_the_same_spend_twice_is_one_spend(db_session):
    reader = await _reader(db_session)
    await _fill(db_session, reader, 10)
    key = f"spend:d:{reader}"
    first = await spend(db_session, reader, amount=3, idempotency_key=key, actor=SYSTEM)
    again = await spend(db_session, reader, amount=3, idempotency_key=key, actor=SYSTEM)
    assert (again.created, again.txn.id) == (False, first.txn.id)
    assert await balance(db_session, reader) == 7
    with pytest.raises(IdempotencyConflict):
        await spend(db_session, reader, amount=4, idempotency_key=key, actor=SYSTEM)


async def test_a_key_belongs_to_one_reader_and_one_kind(db_session):
    reader, other = await _reader(db_session), await _reader(db_session)
    await _fill(db_session, reader, 10)
    await _fill(db_session, other, 10)
    key = f"spend:e:{reader}"
    await spend(db_session, reader, amount=1, idempotency_key=key, actor=SYSTEM)
    with pytest.raises(IdempotencyConflict):
        await spend(db_session, other, amount=1, idempotency_key=key, actor=SYSTEM)
    adj = f"adj:{uuid.uuid4().hex}"
    await adjust(
        db_session, reader, amount=1, cap=100, reason="r", idempotency_key=adj, actor=ADMIN
    )
    with pytest.raises(IdempotencyConflict):
        await adjust(
            db_session, reader, amount=2, cap=100, reason="r", idempotency_key=adj, actor=ADMIN
        )


# --- admin adjustments --------------------------------------------------------------------------


async def test_an_adjustment_up_is_held_to_the_cap_unless_overridden(db_session):
    reader = await _reader(db_session)
    await _fill(db_session, reader, 990)
    with pytest.raises(CapExceeded):
        await adjust(
            db_session, reader, amount=20, cap=1000, reason="goodwill",
            idempotency_key=f"adj:{uuid.uuid4().hex}", actor=ADMIN,
        )  # fmt: skip
    over = await adjust(
        db_session, reader, amount=20, override_cap=True, reason="goodwill, over the cap",
        idempotency_key=f"adj:{uuid.uuid4().hex}", actor=ADMIN,
    )  # fmt: skip
    assert (over.txn.balance_after, over.txn.cap, over.txn.meta) == (
        1010,
        None,
        {"override_cap": True},
    )
    assert over.txn.actor == {"kind": "human", "id": "admin:test"}
    await proven(db_session)


async def test_an_adjustment_down_never_goes_below_zero(db_session):
    reader = await _reader(db_session)
    await _fill(db_session, reader, 5)
    with pytest.raises(InsufficientCoins):
        await adjust(
            db_session, reader, amount=-6, reason="mistake",
            idempotency_key=f"adj:{uuid.uuid4().hex}", actor=ADMIN,
        )  # fmt: skip
    down = await adjust(
        db_session, reader, amount=-5, reason="mistake", idempotency_key=f"adj:{uuid.uuid4().hex}",
        actor=ADMIN,
    )  # fmt: skip
    assert (down.txn.balance_after, down.txn.cap) == (0, None)
    await proven(db_session)


async def test_an_adjustment_says_why(db_session):
    reader = await _reader(db_session)
    with pytest.raises(CoinError, match="reason"):
        await adjust(
            db_session, reader, amount=1, cap=100, reason="  ",
            idempotency_key=f"adj:{uuid.uuid4().hex}", actor=ADMIN,
        )  # fmt: skip
    with pytest.raises(CoinError, match="cap"):
        await adjust(
            db_session, reader, amount=1, reason="r", idempotency_key=f"adj:{uuid.uuid4().hex}",
            actor=ADMIN,
        )  # fmt: skip


# --- what the database refuses on its own -------------------------------------------------------


async def _refused(session, sql: str, **params) -> None:
    with pytest.raises(DBAPIError):
        async with session.begin_nested():
            await session.execute(text(sql), params)


async def _a_txn(session) -> CoinTxn:
    reader = await _reader(session)
    await _fill(session, reader, 10)
    return await session.scalar(select(CoinTxn).where(CoinTxn.reader_id == reader))


async def test_ledger_rows_are_never_changed_or_deleted(db_session):
    txn = await _a_txn(db_session)
    entry = await db_session.scalar(select(CoinEntry.id).where(CoinEntry.txn_id == txn.id))
    await _refused(db_session, "UPDATE coin_txns SET amount = 11 WHERE id = :i", i=txn.id)
    await _refused(db_session, "DELETE FROM coin_txns WHERE id = :i", i=txn.id)
    await _refused(db_session, "UPDATE coin_entries SET amount = 11 WHERE id = :i", i=entry)
    await _refused(db_session, "DELETE FROM coin_entries WHERE id = :i", i=entry)
    await _refused(
        db_session, "UPDATE coin_accounts SET system_key = 'BURN' WHERE system_key = 'ISSUANCE'"
    )
    await _refused(db_session, "DELETE FROM coin_accounts WHERE system_key = 'BURN'")
    await _refused(db_session, "DELETE FROM coin_wallets WHERE reader_id = :i", i=txn.reader_id)
    await _refused(
        db_session, "UPDATE coin_wallets SET account_id = gen_random_uuid() WHERE reader_id = :i",
        i=txn.reader_id,
    )  # fmt: skip


async def test_a_wallet_that_disagrees_with_its_entries_does_not_commit(db_session):
    txn = await _a_txn(db_session)
    with pytest.raises(DBAPIError, match="entries sum to"):
        async with db_session.begin_nested():
            await db_session.execute(
                text("UPDATE coin_wallets SET balance = balance + 1 WHERE reader_id = :i"),
                {"i": txn.reader_id},
            )
            await db_session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))


async def test_a_transaction_whose_entries_do_not_balance_does_not_commit(db_session):
    txn = await _a_txn(db_session)
    burn = await db_session.scalar(text("SELECT id FROM coin_accounts WHERE system_key = 'BURN'"))
    with pytest.raises(DBAPIError, match="does not balance"):
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "INSERT INTO coin_entries (id, txn_id, account_id, amount) "
                    "VALUES (gen_random_uuid(), :t, :a, 1)"
                ),
                {"t": txn.id, "a": burn},
            )
            await db_session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))


@pytest.mark.parametrize(
    ("kind", "amount", "key", "cap", "requested", "after", "constraint"),
    [
        ("SPEND", 5, "spend:x", None, None, 5, "amount_sign_matches_kind"),
        ("MONTHLY_GRANT", 5, "spend:x", 10, 5, 5, "key_names_its_kind"),
        ("MONTHLY_GRANT", 5, "grant:x", 4, 5, 5, "within_cap"),
        ("MONTHLY_GRANT", 6, "grant:x", 10, 5, 6, "never_more_than_requested"),
        ("MONTHLY_GRANT", 5, "grant:x", None, None, 5, "a_grant_says_what_and_up_to"),
        ("SPEND", -5, "spend:x", None, None, -1, "balance_after_not_negative"),
        ("SPEND", -5, "spend:bad key", None, None, 0, "idempotency_key_format"),
        ("ADMIN_ADJUSTMENT", 5, "adj:x", None, None, 5, "adjustment_has_a_reason"),
        ("PURCHASE", 5, "spend:x", None, None, 5, "kind_valid|key_names_its_kind|amount_sign"),
    ],
)
async def test_the_table_refuses_what_the_rules_forbid(
    db_session, kind, amount, key, cap, requested, after, constraint
):
    reader = await _reader(db_session)
    with pytest.raises(DBAPIError, match=constraint):
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "INSERT INTO coin_txns (id, kind, reader_id, amount, requested, cap,"
                    " balance_after, idempotency_key, actor) VALUES (gen_random_uuid(), :k, :r,"
                    " :a, :q, :c, :b, :key, '{}'::jsonb)"
                ),
                {"k": kind, "r": reader, "a": amount, "q": requested, "c": cap, "b": after,
                 "key": f"{key}{uuid.uuid4().hex[:6]}" if " " not in key else key},
            )  # fmt: skip


async def test_the_cap_stops_raising_a_balance_not_a_balance_already_above_it(db_session):
    """At the table: a 0 grant over a balance above its cap is accepted (D-219, D-220); a grant
    that would raise the balance past its cap is refused."""
    reader = await _reader(db_session)
    insert = (
        "INSERT INTO coin_txns (id, kind, reader_id, amount, requested, cap, balance_after,"
        " idempotency_key, actor) VALUES (gen_random_uuid(), 'MONTHLY_GRANT', :r, :a, 50, 100,"
        " :b, :key, '{}'::jsonb)"
    )
    async with db_session.begin_nested():
        await db_session.execute(
            text(insert), {"r": reader, "a": 0, "b": 850, "key": f"grant:free:{reader}:z"}
        )  # accepted by every CHECK (the commit-time check is not run here)
    with pytest.raises(DBAPIError, match="within_cap"):
        async with db_session.begin_nested():
            await db_session.execute(
                text(insert), {"r": reader, "a": 1, "b": 851, "key": f"grant:free:{reader}:y"}
            )


async def test_a_wallet_is_never_negative(db_session):
    txn = await _a_txn(db_session)
    with pytest.raises(DBAPIError, match="balance_not_negative"):
        async with db_session.begin_nested():
            await db_session.execute(
                text("UPDATE coin_wallets SET balance = -1 WHERE reader_id = :i"),
                {"i": txn.reader_id},
            )


# --- reading ------------------------------------------------------------------------------------


async def test_a_reader_never_written_holds_nothing(db_session):
    reader = await _reader(db_session)
    assert await balance(db_session, reader) == 0
    assert await _count(db_session, CoinWallet, CoinWallet.reader_id == reader) == 0


async def test_the_ledger_reconciles(db_session):
    reader = await _reader(db_session)
    await _fill(db_session, reader, 100)
    spent = await spend(
        db_session, reader, amount=30, idempotency_key=f"spend:f:{reader}", actor=SYSTEM
    )
    await refund(db_session, spent.txn.id, actor=SYSTEM)
    await spend(db_session, reader, amount=10, idempotency_key=f"spend:g:{reader}", actor=SYSTEM)
    await adjust(
        db_session, reader, amount=-5, reason="r", idempotency_key=f"adj:{uuid.uuid4().hex}",
        actor=ADMIN,
    )  # fmt: skip
    await grant(
        db_session, reader, requested=500, cap=50, idempotency_key=_month_key("vip", reader),
        actor=SYSTEM,
    )  # fmt: skip
    await proven(db_session)
    report = await reconcile(db_session)
    assert report.ok, report.problems
    assert report.totals["entries"] == 0
    assert await balance(db_session, reader) == 85


async def test_reconcile_names_what_does_not_add_up(db_session):
    """Before the commit-time check runs, a wallet nudged by hand is what reconcile reports."""
    txn = await _a_txn(db_session)
    nudge = await db_session.begin_nested()
    await db_session.execute(
        text("UPDATE coin_wallets SET balance = balance + 1 WHERE reader_id = :i"),
        {"i": txn.reader_id},
    )
    report = await reconcile(db_session)
    await nudge.rollback()
    assert not report.ok
    assert any(str(txn.reader_id) in p for p in report.problems)
