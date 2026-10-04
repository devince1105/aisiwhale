"""D-188: a figure that joined the strip later reaches the watchlists made before it."""

import uuid

from sqlalchemy import select, text

from autora.accounts.models import Reader, WatchlistItem
from autora.accounts.watchlist import INSERT_AFTER_SQL, insert_after_params


async def _reader(session, keys: list[tuple[str, str]]) -> uuid.UUID:
    reader = Reader(email=f"{uuid.uuid4().hex[:10]}@example.com")
    session.add(reader)
    await session.flush()
    for place, (market, symbol) in enumerate(keys):
        session.add(
            WatchlistItem(reader_id=reader.id, market=market, symbol=symbol, position=place)
        )
    await session.flush()
    return reader.id


async def _list(session, reader_id) -> list[str]:
    rows = await session.scalars(
        select(WatchlistItem)
        .where(WatchlistItem.reader_id == reader_id)
        .order_by(WatchlistItem.position, WatchlistItem.created_at)
    )
    return [row.symbol for row in rows]


async def test_txf1_goes_right_after_the_taiex_on_the_lists_that_have_it(db_session):
    kept = await _reader(db_session, [("market", "TAIEX"), ("tw", "2330"), ("us", "NVDA")])
    own = await _reader(db_session, [("tw", "2330"), ("us", "NVDA")])  # took the TAIEX off
    moved = await _reader(db_session, [("tw", "2330"), ("market", "TAIEX"), ("market", "BTC")])
    already = await _reader(db_session, [("market", "TAIEX"), ("market", "TXF1"), ("tw", "2330")])

    params = insert_after_params(("market", "TAIEX"), ("market", "TXF1"))
    for _ in range(2):  # run twice: the second time changes nothing
        for statement in INSERT_AFTER_SQL:
            await db_session.execute(text(statement), params)
        db_session.expire_all()

    assert await _list(db_session, kept) == ["TAIEX", "TXF1", "2330", "NVDA"]
    assert await _list(db_session, own) == ["2330", "NVDA"]
    assert await _list(db_session, moved) == ["2330", "TAIEX", "TXF1", "BTC"]
    assert await _list(db_session, already) == ["TAIEX", "TXF1", "2330"]
