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
        .order_by(WatchlistItem.position, WatchlistItem.created_at, WatchlistItem.id)
    )
    return [(market, symbol) for market, symbol in rows]


async def _next_position(session: AsyncSession, reader_id: uuid.UUID) -> int:
    last = await session.scalar(
        select(func.max(WatchlistItem.position)).where(WatchlistItem.reader_id == reader_id)
    )
    return (last or 0) + 1


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
        .values(
            id=uuid7(),
            reader_id=reader_id,
            market=market,
            symbol=symbol,
            position=await _next_position(session, reader_id),
        )
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
    first = await _next_position(session, reader.id)
    for place, (market, symbol) in enumerate(defaults[:MAX_ITEMS]):
        await session.execute(
            insert(WatchlistItem)
            .values(
                id=uuid7(),
                reader_id=reader.id,
                market=market,
                symbol=symbol,
                position=first + place,
            )
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


async def reorder(
    session: AsyncSession, reader_id: uuid.UUID, order: list[tuple[str, str]]
) -> None:
    """Put the list in ``order`` (market, symbol). What ``order`` leaves out keeps its place
    after it, in its old order; what it names that is not on the list is ignored."""
    rows = (
        await session.scalars(
            select(WatchlistItem)
            .where(WatchlistItem.reader_id == reader_id)
            .order_by(WatchlistItem.position, WatchlistItem.created_at, WatchlistItem.id)
        )
    ).all()
    by_key = {(row.market, row.symbol): row for row in rows}
    named = [by_key[key] for key in dict.fromkeys(order) if key in by_key]
    rest = [row for row in rows if row not in named]
    for place, row in enumerate([*named, *rest], start=1):
        row.position = place
    await session.flush()


# --- a figure added to the strip later (D-188) ----------------------------------------------

INSERT_AFTER_SQL = (
    # make room after ``after`` on every list that has it and has not ``new`` yet
    """
    UPDATE watchlist_items AS w SET position = w.position + 1
    FROM watchlist_items AS a
    WHERE a.market = :after_market AND a.symbol = :after_symbol
      AND w.reader_id = a.reader_id AND w.position > a.position
      AND NOT EXISTS (
        SELECT 1 FROM watchlist_items AS n
        WHERE n.reader_id = a.reader_id AND n.market = :new_market AND n.symbol = :new_symbol
      )
    """,
    # and put it there
    """
    INSERT INTO watchlist_items (id, reader_id, market, symbol, position, created_at)
    SELECT gen_random_uuid(), a.reader_id, :new_market, :new_symbol, a.position + 1, now()
    FROM watchlist_items AS a
    WHERE a.market = :after_market AND a.symbol = :after_symbol
      AND NOT EXISTS (
        SELECT 1 FROM watchlist_items AS n
        WHERE n.reader_id = a.reader_id AND n.market = :new_market AND n.symbol = :new_symbol
      )
    """,
)
"""A new default goes onto the lists made before it (D-188): right after the figure it follows,
on every list that still has that figure — a reader who took it off has made the list their own.
Run once, by a migration; a list that has it already is left as it is."""


def insert_after_params(after: tuple[str, str], new: tuple[str, str]) -> dict[str, str]:
    return {
        "after_market": after[0],
        "after_symbol": after[1],
        "new_market": new[0],
        "new_symbol": new[1],
    }
