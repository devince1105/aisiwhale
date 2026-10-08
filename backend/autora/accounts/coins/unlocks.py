"""Unlocking a COIN article with Whale Coins (P4, D-249): one spend, one unlock, once.

What an article is and what it costs is the newsroom's; this module is handed the article's id
and today's price, and knows only that a reader paid that much for it. Inside the caller's
transaction (nothing here commits):

1. a reader who already unlocked it has it — nothing is spent, whatever the price is now;
2. otherwise the spend: the reader's wallet is locked and the key
   ``spend:article:{reader}:{article}`` looked up after the lock, so two requests at once spend
   once — the second waits, then finds the first's spend;
3. the unlock, beside the spend that paid for it (``ON CONFLICT DO NOTHING``: the unique
   reader-and-article pair is the last word).

A price changed between two such requests makes the second's spend a different one under the
same key: ``IdempotencyConflict``, and the caller rolls back and looks again.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from autora.accounts.coins.ledger import spend
from autora.accounts.coins.models import ArticleUnlock
from autora.infra.ids import uuid7
from autora.runtime.actor import Actor

REF_TYPE = "article"


def unlock_key(reader_id: uuid.UUID, article_id: uuid.UUID) -> str:
    return f"spend:article:{reader_id}:{article_id}"


@dataclass(frozen=True)
class Unlocked:
    unlock: ArticleUnlock
    created: bool
    """False when the reader had already unlocked it: nothing was spent this time."""


async def unlock_of(
    session: AsyncSession, reader_id: uuid.UUID, article_id: uuid.UUID
) -> ArticleUnlock | None:
    return await session.scalar(
        select(ArticleUnlock).where(
            ArticleUnlock.reader_id == reader_id, ArticleUnlock.article_id == article_id
        )
    )


async def unlocks_of(session: AsyncSession, reader_id: uuid.UUID) -> list[ArticleUnlock]:
    """Every article the reader unlocked, newest first."""
    rows = await session.scalars(
        select(ArticleUnlock)
        .where(ArticleUnlock.reader_id == reader_id)
        .order_by(ArticleUnlock.created_at.desc(), ArticleUnlock.id.desc())
    )
    return list(rows)


async def unlock_article(
    session: AsyncSession,
    reader_id: uuid.UUID,
    article_id: uuid.UUID,
    *,
    price: int,
    actor: Actor,
    meta: dict | None = None,
) -> Unlocked:
    """Spend ``price`` coins on the article and record the unlock, unless it is already theirs.
    ``InsufficientCoins`` when the balance cannot cover it (nothing written)."""
    if (held := await unlock_of(session, reader_id, article_id)) is not None:
        return Unlocked(held, created=False)
    posted = await spend(
        session, reader_id, amount=price, idempotency_key=unlock_key(reader_id, article_id),
        actor=actor, ref_type=REF_TYPE, ref_id=str(article_id),
        meta={"price": price} | (meta or {}),
    )  # fmt: skip
    await session.execute(
        pg_insert(ArticleUnlock)
        .values(
            id=uuid7(),
            reader_id=reader_id,
            article_id=article_id,
            coin_txn_id=posted.txn.id,
            price_paid=price,
        )
        .on_conflict_do_nothing(index_elements=["reader_id", "article_id"])
    )
    held = await unlock_of(session, reader_id, article_id)
    assert held is not None
    return Unlocked(held, created=posted.created and held.coin_txn_id == posted.txn.id)
