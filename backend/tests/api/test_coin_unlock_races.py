"""P4 (D-249): unlocking under real concurrency — separate sessions, real commits.

Twenty requests from one reader for one COIN article at once — a double click, a second tab —
spend once and write one unlock; the commit-time checks run on every commit, and the ledger
reconciles after.
"""

import asyncio
import uuid

from sqlalchemy import func, select

from autora.accounts import Reader
from autora.accounts.coins import (
    ArticleUnlock,
    CoinTxn,
    InsufficientCoins,
    TxnKind,
    balance,
    grant,
    reconcile,
    unlock_article,
)
from autora.runtime.actor import Actor

SYSTEM = Actor.system("unlock-race")


async def _reader_with(committed, coins: int) -> uuid.UUID:
    async with committed() as session:
        reader = Reader(email=f"unlock{uuid.uuid4().hex[:12]}@example.com")
        session.add(reader)
        await session.flush()
        await grant(
            session, reader.id, requested=coins, cap=coins, kind=TxnKind.PROMOTION_GRANT,
            idempotency_key=f"promo:unlock:{reader.id}", actor=SYSTEM,
        )  # fmt: skip
        await session.commit()
        return reader.id


async def _unlock(committed, reader_id, article_id, price) -> str:
    async with committed() as session:
        try:
            done = await unlock_article(
                session,
                reader_id,
                article_id,
                price=price,
                actor=Actor.human(f"reader:{reader_id}"),
            )
        except InsufficientCoins:
            await session.rollback()
            return "short"
        await session.commit()
        return "paid" if done.created else "already"


async def test_twenty_unlocks_at_once_are_one(newsroom_room, committed):
    article_id = uuid.UUID(await newsroom_room.publish())
    reader = await _reader_with(committed, 50)
    outcomes = await asyncio.gather(*(_unlock(committed, reader, article_id, 5) for _ in range(20)))
    assert outcomes.count("paid") == 1
    assert outcomes.count("already") == 19
    async with committed() as session:
        assert await balance(session, reader) == 45
        spends = await session.scalar(
            select(func.count()).where(CoinTxn.reader_id == reader, CoinTxn.kind == "SPEND")
        )
        unlocks = await session.scalar(
            select(func.count()).where(ArticleUnlock.reader_id == reader)
        )
        assert (spends, unlocks) == (1, 1)
        report = await reconcile(session)
    assert report.ok, report.problems


async def test_the_repeats_of_a_paid_unlock_are_never_short(newsroom_room, committed):
    """Holding exactly the price: the first pays it all, and the rest find it paid — none is
    told it cannot afford what it already has."""
    article_id = uuid.UUID(await newsroom_room.publish())
    reader = await _reader_with(committed, 5)
    outcomes = await asyncio.gather(*(_unlock(committed, reader, article_id, 5) for _ in range(10)))
    assert (outcomes.count("paid"), outcomes.count("already"), outcomes.count("short")) == (1, 9, 0)
    async with committed() as session:
        assert await balance(session, reader) == 0
