from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from autora.db.models import Approval, ApprovalState
from autora.runtime.approvals import ApprovalError
from autora_api.deps import Operator, RuntimeDep, Session
from autora_api.pagination import Listing, Page, page_rows, search, sort_by

router = APIRouter(prefix="/api/approvals", tags=["approvals"])


class ApprovalOut(BaseModel):
    id: uuid.UUID
    company_id: uuid.UUID
    kind: str
    ref_type: str
    ref_id: uuid.UUID
    task_id: uuid.UUID | None
    run_id: uuid.UUID | None
    action: str | None
    payload: dict[str, Any]
    summary: str
    requested_by: dict[str, Any]
    state: str
    expires_at: datetime | None
    decided_by: dict[str, Any] | None
    decided_at: datetime | None
    reason: str | None
    created_at: datetime


class ApprovalPage(Page[ApprovalOut]):
    pass


ApprovalSort = Literal["created_at", "-created_at"]


class DecisionIn(BaseModel):
    decision: Literal["approve", "reject", "revise"]
    """``revise``: send it back with changes asked for (D-044); needs a ``reason``."""
    reason: str | None = Field(default=None, max_length=8000)
    """Up to 8,000 characters (D-139): what to change, all of it passed to the writer."""


@router.get("")
async def list_approvals(
    session: Session,
    _: Operator,
    company_id: uuid.UUID,
    listing: Listing,
    state: ApprovalState | None = ApprovalState.PENDING,
    sort: ApprovalSort = "created_at",
) -> ApprovalPage:
    """The approval inbox, a page at a time (AD-04). Oldest first by default, so the
    longest-waiting request is on top; ``q`` searches the summary, kind and action."""
    stmt = select(Approval).where(Approval.company_id == company_id)
    if state is not None:
        stmt = stmt.where(Approval.state == state)
    if (
        words := search(listing.words, Approval.summary, Approval.kind, Approval.action)
    ) is not None:
        stmt = stmt.where(words)
    rows, next_cursor, total = await page_rows(
        session,
        stmt,
        sort=sort_by(sort, {"created_at": Approval.created_at}),
        id_column=Approval.id,
        listing=listing,
    )
    return ApprovalPage(
        items=[ApprovalOut.model_validate(row, from_attributes=True) for (row,) in rows],
        next_cursor=next_cursor,
        total=total,
    )


@router.post("/{approval_id}/decide")
async def decide(
    approval_id: uuid.UUID,
    body: DecisionIn,
    session: Session,
    operator: Operator,
    runtime: RuntimeDep,
) -> ApprovalOut:
    try:
        approval = await runtime.approvals.decide(
            session, approval_id, outcome=body.decision, actor=operator, reason=body.reason
        )
    except ApprovalError as exc:
        missing = "not found" in str(exc)
        code = status.HTTP_404_NOT_FOUND if missing else status.HTTP_409_CONFLICT
        raise HTTPException(code, str(exc)) from exc
    await session.commit()
    return ApprovalOut.model_validate(approval, from_attributes=True)
