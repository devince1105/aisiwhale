"""Whale Coins in the back office (P3-C-2, D-235): a reader's wallet, an adjustment, the check.

- GET  /api/admin/coins/wallet?email=&company=&cursor=&limit= -> the reader, their tier and its
  cap, the balance, and every movement newest first — with who made it and why
- POST /api/admin/coins/adjustments {email, amount, reason, override_cap, request_id, company?}
  -> 201 the adjustment; 200 when this request_id was already done just so; 409 when it named
  another; 422 past the cap without an override, below zero, or not a valid adjustment
- GET  /api/admin/coins/reconcile -> the whole ledger checked against itself (read only)

The back office's own (``Operator``). The adjustment's actor is whoever ``require_operator`` let
in — the admin making it (``admin:<their reader id>``) or the operator token — never the reader
whose wallet changes. Every write here is recorded by the audit door (AD-06) on its way out.

The cap is the reader's tier's (``policy.MONTHLY``), for the tier ``/me`` would give them; going
past it is an explicit ``override_cap``, written on the movement (D-220). A movement is never
edited or deleted: a mistake is put right by another adjustment. Looking at a wallet or checking
the ledger writes nothing.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, HTTPException, Query, Response, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select

from autora.accounts import AccountError, Reader, by_email, coins
from autora.accounts.coins import CoinTxn, policy
from autora.accounts.entitlement import entitlement_for
from autora_api.deps import Operator, Session
from autora_api.pagination import Listing, Page, page_rows, sort_by
from autora_api.routers.auth import company_id_for

router = APIRouter(prefix="/api/admin/coins", tags=["admin-coins"])

CompanySlug = Annotated[str | None, Query(max_length=100)]
NEWEST_FIRST = sort_by("-occurred_at", {"occurred_at": CoinTxn.occurred_at})

MAX_ADJUSTMENT = 10_000
"""The most one adjustment may move, either way: a guard against a typed extra zero."""
REASON_MAX = 500


class AdminMovement(BaseModel):
    id: uuid.UUID
    kind: str
    amount: int
    balance_after: int
    occurred_at: datetime
    requested: int | None
    cap: int | None
    idempotency_key: str
    reverses_txn_id: uuid.UUID | None
    ref_type: str | None
    ref_id: str | None
    actor: dict[str, Any]
    reason: str | None
    meta: dict[str, Any]


class AdminWallet(BaseModel):
    reader_id: uuid.UUID
    email: str
    tier: Literal["free", "vip"]
    cap: int
    """The tier's cap: an adjustment up stops here unless overridden."""
    balance: int
    history: Page[AdminMovement]


class Adjustment(BaseModel):
    email: str = Field(max_length=254)
    amount: int = Field(ge=-MAX_ADJUSTMENT, le=MAX_ADJUSTMENT)
    """Up when positive, down when negative; never 0."""
    reason: str = Field(min_length=1, max_length=REASON_MAX)
    override_cap: bool = False
    request_id: uuid.UUID
    """Made by the form once, kept on a retry: the same request is one adjustment."""
    company: str | None = Field(default=None, max_length=100)

    @field_validator("amount")
    @classmethod
    def _moves(cls, amount: int) -> int:
        if amount == 0:
            raise ValueError("an adjustment moves coins")
        return amount

    @field_validator("reason")
    @classmethod
    def _says_why(cls, reason: str) -> str:
        if not reason.strip():
            raise ValueError("an adjustment needs a reason")
        return reason.strip()


class Reconciliation(BaseModel):
    ok: bool
    problems: list[str]
    totals: dict[str, int]


def _view(txn: CoinTxn) -> AdminMovement:
    return AdminMovement(
        id=txn.id,
        kind=txn.kind,
        amount=txn.amount,
        balance_after=txn.balance_after,
        occurred_at=txn.occurred_at,
        requested=txn.requested,
        cap=txn.cap,
        idempotency_key=txn.idempotency_key,
        reverses_txn_id=txn.reverses_txn_id,
        ref_type=txn.ref_type,
        ref_id=txn.ref_id,
        actor=txn.actor,
        reason=txn.reason,
        meta=txn.meta,
    )


async def _reader(session, email: str) -> Reader:
    try:
        reader = await by_email(session, email)
    except AccountError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    if reader is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no reader has this address")
    return reader


async def _tier_cap(session, reader: Reader, company: str | None) -> tuple[str, int]:
    """The tier ``/me`` would give this reader, and its cap."""
    granted = await entitlement_for(
        session, reader, company_id=await company_id_for(session, company)
    )
    terms = policy.MONTHLY.get(granted.tier)
    assert terms is not None, "a signed-up reader is free or vip"
    return granted.tier.value, terms.cap


@router.get("/wallet")
async def get_wallet(
    session: Session,
    _: Operator,
    listing: Listing,
    email: Annotated[str, Query(max_length=254)],
    company: CompanySlug = None,
) -> AdminWallet:
    reader = await _reader(session, email)
    tier, cap = await _tier_cap(session, reader, company)
    rows, next_cursor, total = await page_rows(
        session,
        select(CoinTxn).where(CoinTxn.reader_id == reader.id),
        sort=NEWEST_FIRST,
        id_column=CoinTxn.id,
        listing=listing,
    )
    return AdminWallet(
        reader_id=reader.id,
        email=reader.email,
        tier=tier,
        cap=cap,
        balance=await coins.balance(session, reader.id),
        history=Page(items=[_view(row[0]) for row in rows], next_cursor=next_cursor, total=total),
    )


@router.post("/adjustments", status_code=status.HTTP_201_CREATED)
async def adjust_coins(
    body: Adjustment, session: Session, actor: Operator, response: Response
) -> AdminMovement:
    reader = await _reader(session, body.email)
    tier, cap = await _tier_cap(session, reader, body.company)
    try:
        posted = await coins.adjust(
            session,
            reader.id,
            amount=body.amount,
            reason=body.reason,
            idempotency_key=f"adj:{body.request_id}",
            actor=actor,
            cap=None if body.override_cap else cap,
            override_cap=body.override_cap,
            meta={"tier": tier, "tier_cap": cap},
        )
    except coins.IdempotencyConflict as exc:
        await session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except (coins.CapExceeded, coins.InsufficientCoins, coins.CoinError) as exc:
        await session.rollback()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    view = _view(posted.txn)
    await session.commit()
    if not posted.created:
        response.status_code = status.HTTP_200_OK
    return view


@router.get("/reconcile")
async def reconcile_coins(session: Session, _: Operator) -> Reconciliation:
    report = await coins.reconcile(session)
    return Reconciliation(ok=report.ok, problems=report.problems, totals=report.totals)
