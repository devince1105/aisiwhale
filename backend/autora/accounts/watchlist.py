"""A reader's own watchlist (D-060): the stocks they keep an eye on, in the order they added them.

Which stocks may be on it is the site's to say (the stocks with a page); this keeps what a reader
chose, and nothing about what those stocks are.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from autora.accounts.models import Reader, WatchlistItem
from autora.infra.ids import uuid7

MAX_ITEMS = 50


class WatchlistFull(Exception):
    pass


async def items(session: AsyncSession, reader_id: uuid.UUID) -> list[tuple[str, str]]:
    """(market, symbol), oldest first."""
    rows = await session.execute(
        select(WatchlistItem.market, WatchlistItem.symbol)
        .where(WatchlistItem.reader_id == reader_id)
        .order_by(WatchlistItem.created_at, WatchlistItem.id)
    )
    return [(market, symbol) for market, symbol in rows]


async def add(session: AsyncSession, reader_id: uuid.UUID, market: str, symbol: str) -> None:
    """Keep a stock on the list; adding it again changes nothing."""
    count = await session.scalar(
        select(func.count()).select_from(WatchlistItem).where(WatchlistItem.reader_id == reader_id)
    )
    if (count or 0) >= MAX_ITEMS:
        raise WatchlistFull(f"a watchlist keeps at most {MAX_ITEMS} stocks")
    await session.execute(
        insert(WatchlistItem)
        # uuid7: ordered by when it was made, so two added in one transaction keep their order
        .values(id=uuid7(), reader_id=reader_id, market=market, symbol=symbol)
        .on_conflict_do_nothing(index_elements=["reader_id", "market", "symbol"])
    )


async def start(
    session: AsyncSession,
    reader: Reader,
    defaults: list[tuple[str, str]],
    *,
    now: datetime | None = None,
) -> bool:
    """A reader's first look at their watchlist: fill it with ``defaults`` (market, symbol),
    once. True when it was filled now."""
    if reader.watchlist_started_at is not None:
        return False
    reader.watchlist_started_at = now or datetime.now(UTC)
    for market, symbol in defaults[:MAX_ITEMS]:
        await session.execute(
            insert(WatchlistItem)
            .values(id=uuid7(), reader_id=reader.id, market=market, symbol=symbol)
            .on_conflict_do_nothing(index_elements=["reader_id", "market", "symbol"])
        )
    await session.flush()
    return True


async def remove(session: AsyncSession, reader_id: uuid.UUID, market: str, symbol: str) -> None:
    await session.execute(
        delete(WatchlistItem).where(
            WatchlistItem.reader_id == reader_id,
            WatchlistItem.market == market,
            WatchlistItem.symbol == symbol,
        )
    )
