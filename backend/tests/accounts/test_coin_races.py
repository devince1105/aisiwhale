"""P3-A: the Whale Coin ledger under real concurrency — separate sessions, real commits.

Each test makes its own readers, so what these commit (and the ledger never deletes) does not
meet another test's rows. The commit-time checks run on every commit here.
"""

import asyncio
import uuid

from sqlalchemy import func, select

from autora.accounts import Reader
from autora.accounts.coins import (
    CoinAccount,
    CoinTxn,
    CoinWallet,
    IdempotencyConflict,
    InsufficientCoins,
    TxnKind,
    balance,
    grant,
    reconcile,
    spend,
)
from autora.runtime.actor import Actor

SYSTEM = Actor.system("coins-race")


async def _reader_with(committed, coins: int) -> uuid.UUID:
    async with committed() as session:
        reader = Reader(email=f"race{uuid.uuid4().hex[:12]}@example.com")
        session.add(reader)
        await session.flush()
        if coins:
            await grant(
                session, reader.id, requested=coins, cap=coins, kind=TxnKind.PROMOTION_GRANT,
                idempotency_key=f"promo:race:{reader.id}", actor=SYSTEM,
            )  # fmt: skip
        await session.commit()
        return reader.id


async def _spend(committed, reader_id, amount, key) -> str:
    async with committed() as session:
        try:
            posted = await spend(
                session, reader_id, amount=amount, idempotency_key=key, actor=SYSTEM
            )
        except InsufficientCoins:
            await session.rollback()
            return "short"
        except IdempotencyConflict:
            await session.rollback()
            return "conflict"
        await session.commit()
        return "spent" if posted.created else "repeat"


async def test_a_hundred_spends_at_once_never_take_more_than_was_held(committed):
    reader = await _reader_with(committed, 100)
    outcomes = await asyncio.gather(
        *(_spend(committed, reader, 5, f"spend:race:{reader}:{i}") for i in range(100))
    )
    assert outcomes.count("spent") == 20
    assert outcomes.count("short") == 80
    async with committed() as session:
        assert await balance(session, reader) == 0
        spends = await session.scalar(
            select(func.count()).where(CoinTxn.reader_id == reader, CoinTxn.kind == "SPEND")
        )
        assert spends == 20
        report = await reconcile(session)
    assert report.ok, report.problems


async def test_a_hundred_requests_with_one_key_are_one_spend(committed):
    reader = await _reader_with(committed, 100)
    key = f"spend:once:{reader}"
    outcomes = await asyncio.gather(*(_spend(committed, reader, 7, key) for _ in range(100)))
    assert outcomes.count("spent") == 1
    assert outcomes.count("repeat") == 99
    async with committed() as session:
        assert await balance(session, reader) == 93
        assert await session.scalar(
            select(func.count()).where(CoinTxn.idempotency_key == key)
        ) == 1  # fmt: skip


async def test_first_grants_at_once_make_one_wallet_and_stop_at_the_cap(committed):
    """Fifty different grants for a reader with no wallet yet: one account, one wallet, and
    together never past the cap."""
    async with committed() as session:
        reader = Reader(email=f"race{uuid.uuid4().hex[:12]}@example.com")
        session.add(reader)
        await session.commit()
        reader_id = reader.id

    async def one(i: int) -> int:
        async with committed() as session:
            posted = await grant(
                session, reader_id, requested=30, cap=1000, kind=TxnKind.PROMOTION_GRANT,
                idempotency_key=f"promo:race{i}:{reader_id}", actor=SYSTEM,
            )  # fmt: skip
            await session.commit()
            return posted.txn.amount

    given = await asyncio.gather(*(one(i) for i in range(50)))
    assert sorted(given, reverse=True) == [30] * 33 + [10] + [0] * 16
    async with committed() as session:
        assert await balance(session, reader_id) == 1000
        assert await session.scalar(
            select(func.count()).where(CoinAccount.reader_id == reader_id)
        ) == 1  # fmt: skip
        assert await session.scalar(
            select(func.count()).where(CoinWallet.reader_id == reader_id)
        ) == 1  # fmt: skip
        report = await reconcile(session)
    assert report.ok, report.problems
