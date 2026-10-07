"""How the approvals have gone (AD-12, D-234; the ERP's GetReportAsync, logs/admin/01 §2.2).

- GET /api/approvals/report?company_id=&days=30&stuck_hours=24
  → over the last ``days``: how many were decided and how (approved, sent back, rejected), how
  many ran out and were asked again (D-001, D-131), how long a decision took (median, P90), the
  same by kind (an article, a command, an official report…) and by who decided; and what has
  waited longer than ``stuck_hours`` now.

Any back-office role may read it. Times are hours; a rate is of what was decided.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import and_, func, select

from autora.db.models import Approval, ApprovalState
from autora_api.deps import Operator, Session
from autora_api.routers.admin_audit import _label, _labels

router = APIRouter(prefix="/api/approvals", tags=["approvals"])

DECIDED = (ApprovalState.APPROVED, ApprovalState.RETURNED, ApprovalState.REJECTED)
STUCK_LISTED = 20


class Outcomes(BaseModel):
    decided: int
    approved: int
    returned: int
    rejected: int
    expired: int
    """Ran out undecided; each was asked again at once (D-131)."""
    median_hours: float | None
    p90_hours: float | None


class KindOutcomes(Outcomes):
    kind: str


class Decider(BaseModel):
    actor: dict[str, Any]
    label: str
    decided: int
    approved: int
    returned: int
    rejected: int


class Stuck(BaseModel):
    id: uuid.UUID
    kind: str
    summary: str
    waited_hours: float
    expires_at: datetime | None


class ApprovalReport(BaseModel):
    since: datetime
    days: int
    total: Outcomes
    kinds: list[KindOutcomes]
    deciders: list[Decider]
    pending: int
    stuck_hours: int
    stuck: list[Stuck]
    """The oldest pending past ``stuck_hours``, at most 20."""
    stuck_total: int


def _hours(column):
    return func.extract("epoch", column) / 3600.0


async def _outcomes(session, base, since: datetime) -> dict[str | None, dict[str, Any]]:
    """By kind (key None: all), the counts and the decision times."""
    took = _hours(Approval.decided_at - Approval.created_at)
    decided = and_(Approval.state.in_([s.value for s in DECIDED]), Approval.decided_at >= since)
    expired = and_(Approval.state == ApprovalState.EXPIRED.value, Approval.updated_at >= since)

    def counts(*group):
        return select(
            *group,
            func.count().filter(decided).label("decided"),
            func.count().filter(and_(decided, Approval.state == "APPROVED")).label("approved"),
            func.count().filter(and_(decided, Approval.state == "RETURNED")).label("returned"),
            func.count().filter(and_(decided, Approval.state == "REJECTED")).label("rejected"),
            func.count().filter(expired).label("expired"),
            func.percentile_cont(0.5).within_group(took).filter(decided).label("median"),
            func.percentile_cont(0.9).within_group(took).filter(decided).label("p90"),
        ).where(base)

    out: dict[str | None, dict[str, Any]] = {}
    for row in (await session.execute(counts(Approval.kind).group_by(Approval.kind))).mappings():
        out[row["kind"]] = dict(row)
    total = (await session.execute(counts())).mappings().one()
    out[None] = dict(total)
    return out


def _model(row: dict[str, Any]) -> dict[str, Any]:
    def rounded(value):
        return round(float(value), 1) if value is not None else None

    return {
        "decided": row["decided"],
        "approved": row["approved"],
        "returned": row["returned"],
        "rejected": row["rejected"],
        "expired": row["expired"],
        "median_hours": rounded(row["median"]),
        "p90_hours": rounded(row["p90"]),
    }


@router.get("/report")
async def approval_report(
    session: Session,
    _: Operator,
    company_id: uuid.UUID,
    days: Annotated[int, Query(ge=1, le=365)] = 30,
    stuck_hours: Annotated[int, Query(ge=1, le=24 * 30)] = 24,
) -> ApprovalReport:
    now = datetime.now(UTC)
    since = now - timedelta(days=days)
    base = Approval.company_id == company_id
    by_kind = await _outcomes(session, base, since)
    total = by_kind.pop(None)
    kinds = sorted(
        (KindOutcomes(kind=kind, **_model(row)) for kind, row in by_kind.items()),
        key=lambda k: (-(k.decided + k.expired), k.kind),
    )
    kinds = [k for k in kinds if k.decided or k.expired]

    deciders_rows = (
        await session.execute(
            select(
                Approval.decided_by,
                func.count().label("decided"),
                func.count().filter(Approval.state == "APPROVED").label("approved"),
                func.count().filter(Approval.state == "RETURNED").label("returned"),
                func.count().filter(Approval.state == "REJECTED").label("rejected"),
            )
            .where(
                base, Approval.state.in_([s.value for s in DECIDED]), Approval.decided_at >= since
            )
            .group_by(Approval.decided_by)
            .order_by(func.count().desc())
        )
    ).all()
    names = await _labels(session, [row.decided_by for row in deciders_rows if row.decided_by])
    deciders = [
        Decider(
            actor=row.decided_by or {},
            label=_label(row.decided_by or {}, names),
            decided=row.decided,
            approved=row.approved,
            returned=row.returned,
            rejected=row.rejected,
        )
        for row in deciders_rows
    ]

    pending = Approval.state == ApprovalState.PENDING.value
    late = and_(base, pending, Approval.created_at <= now - timedelta(hours=stuck_hours))
    stuck_rows = (
        await session.scalars(
            select(Approval)
            .where(late)
            .order_by(Approval.created_at, Approval.id)
            .limit(STUCK_LISTED)
        )
    ).all()
    return ApprovalReport(
        since=since,
        days=days,
        total=Outcomes(**_model(total)),
        kinds=kinds,
        deciders=deciders,
        pending=await session.scalar(select(func.count()).where(base, pending)) or 0,
        stuck_hours=stuck_hours,
        stuck=[
            Stuck(
                id=a.id,
                kind=a.kind,
                summary=a.summary,
                waited_hours=round((now - a.created_at).total_seconds() / 3600, 1),
                expires_at=a.expires_at,
            )
            for a in stuck_rows
        ],
        stuck_total=await session.scalar(select(func.count()).where(late)) or 0,
    )
