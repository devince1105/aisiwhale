"""A signed-in reader's Whale Coins (P3-C, D-235, D-238): to look at, nothing more.

- GET /api/me/coins?company=&cursor=&limit= -> the balance, the month's terms for their tier,
  and their movements, newest first, a page at a time

Read only: it grants nothing (``/api/auth/me`` does, when grants are on), spends nothing
(``/api/me/unlocks`` does, P4),
and does not touch ``last_seen_at``. The reader is whoever the cookie says. The tier, the
month, its terms and whether it was given are the grant's own answers (``coins.this_month``,
``policy``), worked out for the company ``/me`` would use — so this page and the header agree.

What a reader sees of a movement is its kind, amount, balance after and when; not who made it,
why an admin did, its key or its notes. A spend on an article (P4, D-249) names the article:
its title, and its page while it is on the site.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Cookie, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select

from autora.accounts import SESSION_COOKIE, coins, reader_for
from autora.accounts.coins import CoinTxn, policy
from autora.accounts.coins.unlocks import REF_TYPE as ARTICLE
from autora.accounts.entitlement import Capability, entitlement_for
from autora.domains.newsroom.models import Article
from autora.domains.newsroom.publisher import article_path
from autora_api.deps import Session
from autora_api.pagination import Listing, Page, page_rows, sort_by
from autora_api.routers.auth import company_id_for

router = APIRouter(prefix="/api/me/coins", tags=["coins"])

SessionCookie = Annotated[str | None, Cookie(alias=SESSION_COOKIE)]
CompanySlug = Annotated[str | None, Query(max_length=100)]

NEWEST_FIRST = sort_by("-occurred_at", {"occurred_at": CoinTxn.occurred_at})


class Monthly(BaseModel):
    amount: int | None
    """What the tier gives a month; None for a tier that gets nothing."""
    cap: int | None
    """The wallet cap a monthly grant stops at."""
    month: str
    """``YYYY-MM`` in Taipei."""
    granted: bool
    """This month's grant for this tier is written (0 when the wallet was already at its cap)."""
    grants_on: bool
    """Whether monthly grants are on yet (D-238); off, the page says they are coming."""


class CoinArticle(BaseModel):
    title: str
    path: str | None
    """Its page, while it is on the site; None once taken down."""


class CoinMovement(BaseModel):
    id: uuid.UUID
    kind: str
    """MONTHLY_GRANT, PROMOTION_GRANT, ADMIN_ADJUSTMENT, SPEND or REFUND."""
    amount: int
    """The signed change to the wallet."""
    balance_after: int
    occurred_at: datetime
    month: str | None = None
    """For a monthly grant: the month it was for."""
    ref_type: str | None = None
    ref_id: str | None = None
    article: CoinArticle | None = None
    """What a spend on an article was for (P4)."""


class CoinWallet(BaseModel):
    balance: int
    tier: Literal["free", "vip"]
    monthly: Monthly
    history: Page[CoinMovement]


def _movement(txn: CoinTxn, articles: dict[str, CoinArticle]) -> CoinMovement:
    return CoinMovement(
        id=txn.id,
        kind=txn.kind,
        amount=txn.amount,
        balance_after=txn.balance_after,
        occurred_at=txn.occurred_at,
        month=txn.meta.get("month") if txn.kind == coins.TxnKind.MONTHLY_GRANT.value else None,
        ref_type=txn.ref_type,
        ref_id=txn.ref_id,
        article=articles.get(txn.ref_id or "") if txn.ref_type == ARTICLE else None,
    )


async def _articles(session, txns: list[CoinTxn]) -> dict[str, CoinArticle]:
    """The articles a page of movements spent coins on, by id: title in its first language."""
    ids = {uuid.UUID(t.ref_id) for t in txns if t.ref_type == ARTICLE and t.ref_id}
    if not ids:
        return {}
    rows = await session.scalars(select(Article).where(Article.id.in_(ids)))
    return {
        str(a.id): CoinArticle(
            title=a.title,
            path=article_path(a.primary_lang, a.slug)
            if a.published_group_id is not None and a.listed and a.primary_lang in a.published_langs
            else None,
        )
        for a in rows
    }


@router.get("")
async def get_coins(
    session: Session,
    listing: Listing,
    company: CompanySlug = None,
    autora_reader: SessionCookie = None,
) -> CoinWallet:
    reader = await reader_for(session, autora_reader)
    if reader is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "sign in to see your coins")
    granted = await entitlement_for(
        session, reader, company_id=await company_id_for(session, company)
    )
    if not granted.can(Capability.COINS):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "no coins here")
    month = await coins.this_month(session, reader.id, granted.tier)
    rows, next_cursor, total = await page_rows(
        session,
        select(CoinTxn).where(CoinTxn.reader_id == reader.id),
        sort=NEWEST_FIRST,
        id_column=CoinTxn.id,
        listing=listing,
    )
    txns = [row[0] for row in rows]
    articles = await _articles(session, txns)
    wallet = CoinWallet(
        balance=await coins.balance(session, reader.id),
        tier=granted.tier.value,
        monthly=Monthly(
            amount=month.terms.amount if month.terms else None,
            cap=month.terms.cap if month.terms else None,
            month=month.month,
            granted=month.granted,
            grants_on=policy.MONTHLY_GRANTS_ON,
        ),
        history=Page(
            items=[_movement(txn, articles) for txn in txns], next_cursor=next_cursor, total=total
        ),
    )
    # read only: nothing is committed, so last_seen_at stays /me's to write
    return wallet
