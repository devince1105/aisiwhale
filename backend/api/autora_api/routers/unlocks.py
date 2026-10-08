"""A signed-in reader's COIN articles (P4, D-249): unlocking one, and what they unlocked.

- POST /api/me/unlocks/{article_id} -> 201 unlocked now, the price spent;
  200 already theirs, nothing spent; 402 {need, held} the balance cannot cover it;
  404 no published COIN article by that id
- GET  /api/me/unlocks -> every article they unlocked, newest first

The reader is whoever the cookie says. The price is the article's at that moment, and it is
theirs for good once paid: a later price, or the article going free and back, changes nothing.
No request id is needed: the spend's key is the reader and the article, so a retry, a double
click or a second tab is the same unlock.
Being VIP does not open a COIN article (D-249) — every reader pays the same coins.

What the newsroom says about the article (is it published, on the site, COIN, at what price)
and what the ledger does with the coins (``coins.unlock_article``) meet here: neither layer
knows the other.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Cookie, HTTPException, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import select

from autora.accounts import SESSION_COOKIE, coins, reader_for
from autora.accounts.entitlement import Capability, entitlement_for
from autora.domains.newsroom.models import Article, ArticleAccess
from autora.runtime.actor import Actor
from autora_api.deps import Session
from autora_api.problems import problem

router = APIRouter(prefix="/api/me/unlocks", tags=["coins"])

SessionCookie = Annotated[str | None, Cookie(alias=SESSION_COOKIE)]


class UnlockResult(BaseModel):
    article_id: uuid.UUID
    unlocked: bool = True
    already: bool
    """True: it was theirs before this request, and nothing was spent."""
    price: int
    """What they paid for it, whenever that was."""
    balance: int


class UnlockedArticle(BaseModel):
    article_id: uuid.UUID
    price_paid: int
    unlocked_at: datetime


async def _signed_in(session, cookie: str | None):
    reader = await reader_for(session, cookie)
    if reader is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "sign in to unlock articles")
    return reader


@router.post("/{article_id}", status_code=status.HTTP_201_CREATED, response_model=UnlockResult)
async def unlock(
    article_id: uuid.UUID, session: Session, response: Response, autora_reader: SessionCookie = None
) -> UnlockResult | JSONResponse:
    reader = await _signed_in(session, autora_reader)
    article = await session.scalar(
        select(Article).where(
            Article.id == article_id,
            Article.published_group_id.is_not(None),
            Article.listed.is_(True),
            Article.access == ArticleAccess.COIN.value,
        )
    )
    if article is None or article.coin_price is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no COIN article {article_id}")
    granted = await entitlement_for(session, reader, company_id=article.company_id)
    if not granted.can(Capability.COINS):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "no coins here")
    reader_id, price, slug = reader.id, article.coin_price, article.slug
    try:
        done = await coins.unlock_article(
            session, reader_id, article_id, price=price,
            actor=Actor.human(f"reader:{reader_id}"), meta={"slug": slug},
        )  # fmt: skip
    except coins.InsufficientCoins:
        held = await coins.balance(session, reader_id)
        await session.rollback()
        return problem(402, "not enough coins", need=price, held=held)
    except coins.IdempotencyConflict:
        # the price changed while another request for it was paying: whatever that one did stands
        await session.rollback()
        held_unlock = await coins.unlock_of(session, reader_id, article_id)
        if held_unlock is None:
            raise HTTPException(status.HTTP_409_CONFLICT, "the price changed; try again") from None
        response.status_code = status.HTTP_200_OK
        return UnlockResult(
            article_id=article_id, already=True, price=held_unlock.price_paid,
            balance=await coins.balance(session, reader_id),
        )  # fmt: skip
    paid = done.unlock.price_paid
    await session.commit()
    if not done.created:
        response.status_code = status.HTTP_200_OK
    return UnlockResult(
        article_id=article_id, already=not done.created, price=paid,
        balance=await coins.balance(session, reader_id),
    )  # fmt: skip


@router.get("")
async def unlocked(session: Session, autora_reader: SessionCookie = None) -> list[UnlockedArticle]:
    """What the reader unlocked: the site marks those 已解鎖 on its lists. A reader's own few, so
    all of them at once."""
    reader = await _signed_in(session, autora_reader)
    return [
        UnlockedArticle(article_id=u.article_id, price_paid=u.price_paid, unlocked_at=u.created_at)
        for u in await coins.unlocks_of(session, reader.id)
    ]
