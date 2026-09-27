"""A signed-in reader's watchlist (D-060): any reader, member or not.

- GET    /api/me/watchlist?lang=         -> the stocks on it, oldest first, with their names
- POST   /api/me/watchlist/{symbol}      -> 204, on it (again: no change)
- DELETE /api/me/watchlist/{symbol}      -> 204, off it

The reader is whoever the site's cookie says, and nobody else: no reader id in any address.
Any listed Taiwan or US stock may be kept (D-061); keeping one tracks it, so its prices are
fetched — the newsroom learns that a stock is wanted, never by whom.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Cookie, HTTPException, Query, Response, status
from pydantic import BaseModel

from autora.accounts import SESSION_COOKIE, reader_for
from autora.accounts import watchlist as reader_watchlist
from autora.domains.newsroom import securities
from autora.domains.newsroom.holdings import Stock
from autora_api.deps import Session

router = APIRouter(prefix="/api/me/watchlist", tags=["watchlist"])

SessionCookie = Annotated[str | None, Cookie(alias=SESSION_COOKIE)]


class WatchedStock(BaseModel):
    symbol: str
    market: str
    key: str
    """As the market strip keys its quotes: ``tw:2330``, ``us:NVDA``."""
    name: str


async def _reader(session: Session, cookie: str | None):
    reader = await reader_for(session, cookie)
    if reader is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "sign in to keep a watchlist")
    return reader


async def _stock(session: Session, symbol: str) -> Stock:
    stock = await securities.find(session, symbol)
    if stock is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no page for {symbol}")
    return stock


@router.get("")
async def get_watchlist(
    session: Session,
    lang: Annotated[
        str, Query(pattern=r"^[a-z]{2}(-[A-Z][A-Za-z]{1,3})?$", max_length=10)
    ] = "zh-TW",
    autora_reader: SessionCookie = None,
) -> list[WatchedStock]:
    reader = await _reader(session, autora_reader)
    out = []
    for market, symbol in await reader_watchlist.items(session, reader.id):
        stock = await securities.find(session, symbol)
        if stock is None or stock.market != market:
            continue  # a stock the site no longer has a page for
        out.append(
            WatchedStock(
                symbol=stock.symbol,
                market=stock.market,
                key=stock.key,
                name=stock.zh if lang.startswith("zh") else stock.en,
            )
        )
    await session.commit()  # last_seen_at
    return out


@router.post("/{symbol}", status_code=status.HTTP_204_NO_CONTENT)
async def watch(symbol: str, session: Session, autora_reader: SessionCookie = None) -> Response:
    reader = await _reader(session, autora_reader)
    stock = await _stock(session, symbol)
    try:
        await reader_watchlist.add(session, reader.id, stock.market, stock.symbol)
        await securities.track(session, stock)
    except reader_watchlist.WatchlistFull as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/{symbol}", status_code=status.HTTP_204_NO_CONTENT)
async def unwatch(symbol: str, session: Session, autora_reader: SessionCookie = None) -> Response:
    reader = await _reader(session, autora_reader)
    stock = await _stock(session, symbol)
    await reader_watchlist.remove(session, reader.id, stock.market, stock.symbol)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
