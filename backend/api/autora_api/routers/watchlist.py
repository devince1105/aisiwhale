"""A signed-in reader's watchlist (D-060): any reader, member or not.

- GET    /api/me/watchlist?lang=         -> what is on it, oldest first, with names
- POST   /api/me/watchlist/{symbol}      -> 204, on it (again: no change)
- DELETE /api/me/watchlist/{symbol}      -> 204, off it
- PUT    /api/me/watchlist {keys}        -> 204, in the order the reader dragged it into (D-063)

The reader is whoever the site's cookie says, and nobody else: no reader id in any address.
Any listed Taiwan or US stock may be kept (D-061); keeping one tracks it, so its prices are
fetched — the newsroom learns that a stock is wanted, never by whom. The market strip's other
figures may be kept too (D-062): its index, rate, oil and coins, quoted as it quotes them, with
no page of their own. A new watchlist starts as the strip is, in its order.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import APIRouter, Cookie, HTTPException, Query, Response, status
from pydantic import BaseModel, Field

from autora.accounts import SESSION_COOKIE, reader_for
from autora.accounts import watchlist as reader_watchlist
from autora.domains.newsroom import securities
from autora.domains.newsroom.forex import CHARTED, NAMES
from autora.domains.newsroom.holdings import Stock
from autora.domains.newsroom.market_strip import ORDER
from autora_api.deps import Session

router = APIRouter(prefix="/api/me/watchlist", tags=["watchlist"])

FIGURES = {
    "TAIEX": ("加權指數", "TAIEX"),
    "NASDAQ": ("那斯達克", "Nasdaq"),
    "US10Y": ("美國10年期公債", "US 10Y"),
    "WTI": ("西德州原油", "WTI crude"),
    "XAU": ("黃金", "Gold"),
    "BTC": ("比特幣", "Bitcoin"),
    "ETH": ("以太幣", "Ether"),
    # every currency with a chart against the New Taiwan dollar (D-072): the strip has three,
    # a reader may keep any of them
    **{f"{code}TWD": NAMES[code] for code in CHARTED},
}
"""The figures that are not stocks, as a watchlist keeps them (market ``market``): the strip's,
and the currencies; the strip keys them in lower case, ``taiex``, ``btc``, ``jpytwd``."""
assert {k for k in ORDER if ":" not in k} <= {key.lower() for key in FIGURES}

DEFAULTS = [
    (key.split(":")[0], key.split(":")[1]) if ":" in key else ("market", key.upper())
    for key in ORDER
]
"""Where a new watchlist starts: everything on the market strip, in its order (D-062)."""

SessionCookie = Annotated[str | None, Cookie(alias=SESSION_COOKIE)]


class WatchedStock(BaseModel):
    symbol: str
    market: str
    """``tw``, ``us``, or ``market`` for the strip's index, rate, oil and coins."""
    key: str
    """As the market strip keys its quotes: ``tw:2330``, ``us:NVDA``, ``btc``."""
    name: str
    exchange: str | None = None
    """TPEx for an over-the-counter Taiwan stock: its code reads .TWO."""


@dataclass(frozen=True)
class _Kept:
    """What a symbol names on a watchlist: a stock (with its page) or one of the strip's other
    figures."""

    market: str
    symbol: str
    key: str
    zh: str
    en: str
    exchange: str | None = None
    stock: Stock | None = None


async def _reader(session: Session, cookie: str | None):
    reader = await reader_for(session, cookie)
    if reader is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "sign in to keep a watchlist")
    return reader


async def _kept(session: Session, symbol: str) -> _Kept | None:
    figure = FIGURES.get(symbol.upper())
    if figure is not None:
        return _Kept("market", symbol.upper(), symbol.lower(), *figure)
    stock = await securities.find(session, symbol)
    if stock is None:
        return None
    return _Kept(stock.market, stock.symbol, stock.key, stock.zh, stock.en, stock.exchange, stock)


async def _required(session: Session, symbol: str) -> _Kept:
    kept = await _kept(session, symbol)
    if kept is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no page for {symbol}")
    return kept


@router.get("")
async def get_watchlist(
    session: Session,
    lang: Annotated[
        str, Query(pattern=r"^[a-z]{2}(-[A-Z][A-Za-z]{1,3})?$", max_length=10)
    ] = "zh-TW",
    autora_reader: SessionCookie = None,
) -> list[WatchedStock]:
    reader = await _reader(session, autora_reader)
    # a first look: the market strip as it is, in its order, as a start to change
    await reader_watchlist.start(session, reader, DEFAULTS)
    out = []
    for market, symbol in await reader_watchlist.items(session, reader.id):
        kept = await _kept(session, symbol)
        if kept is None or kept.market != market:
            continue  # something the site no longer has
        out.append(
            WatchedStock(
                symbol=kept.symbol,
                market=kept.market,
                key=kept.key,
                name=kept.zh if lang.startswith("zh") else kept.en,
                exchange=kept.exchange,
            )
        )
    await session.commit()  # last_seen_at
    return out


class Order(BaseModel):
    keys: list[str] = Field(max_length=reader_watchlist.MAX_ITEMS * 2)
    """The list's keys as ``GET`` gives them (``tw:2330``, ``taiex``), in the new order."""


def _market_symbol(key: str) -> tuple[str, str]:
    market, _, symbol = key.partition(":")
    return (market, symbol) if symbol else ("market", key.upper())


@router.put("", status_code=status.HTTP_204_NO_CONTENT)
async def reorder(body: Order, session: Session, autora_reader: SessionCookie = None) -> Response:
    """The reader's own order (D-063). Keys not on the list are ignored; what the order leaves
    out keeps its place after it."""
    reader = await _reader(session, autora_reader)
    await reader_watchlist.reorder(session, reader.id, [_market_symbol(k) for k in body.keys])
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{symbol}", status_code=status.HTTP_204_NO_CONTENT)
async def watch(symbol: str, session: Session, autora_reader: SessionCookie = None) -> Response:
    reader = await _reader(session, autora_reader)
    kept = await _required(session, symbol)
    await reader_watchlist.start(session, reader, DEFAULTS)  # the defaults first, as on a look
    try:
        await reader_watchlist.add(session, reader.id, kept.market, kept.symbol)
        if kept.stock is not None:
            await securities.track(session, kept.stock)
    except reader_watchlist.WatchlistFull as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/{symbol}", status_code=status.HTTP_204_NO_CONTENT)
async def unwatch(symbol: str, session: Session, autora_reader: SessionCookie = None) -> Response:
    reader = await _reader(session, autora_reader)
    kept = await _required(session, symbol)
    await reader_watchlist.remove(session, reader.id, kept.market, kept.symbol)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
