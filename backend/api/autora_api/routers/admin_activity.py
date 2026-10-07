"""One thing's history, as the back office shows it beside it (AD-07, D-234).

- GET /api/admin/activity?target_type=article|story|approval&target_id=…[&limit=]
  → newest first: its state changes (``state_transitions``), what people did to it in the back
  office (``admin_actions``, AD-06) and — for an article — the approvals that asked about it,
  when each was asked and how it was decided.

Jira's 活動: who did what to this, and what it went through, in one list. Each entry names who
in words (an admin by address, an agent by name, the operator token, a system part).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import select

from autora.accounts.models import Reader
from autora.db.models import AdminAction, Agent, Approval, StateTransition
from autora_api.deps import Operator, Session

router = APIRouter(prefix="/api/admin/activity", tags=["admin-activity"])

Target = Literal["article", "story", "approval"]
MAX = 200
ADMIN = "admin:"


class ActivityEntry(BaseModel):
    at: datetime
    kind: Literal["state", "action", "asked"]
    """``state``: it changed state; ``action``: a person did something to it in the back
    office; ``asked``: an approval about it was asked for."""
    subject: str
    """What changed: the target itself, or one of its approvals (``approval``)."""
    subject_id: str
    actor: dict[str, Any]
    actor_label: str
    from_state: str | None = None
    to_state: str | None = None
    reason: str | None = None
    """A state change's reason, an approval's summary, or a refused action's status text."""
    route: str | None = None
    action: str | None = None
    status: int | None = None


def _uuid(value: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(value)
    except ValueError:
        return None


async def _labels(session, actors: list[dict[str, Any]]) -> dict[str, str]:
    readers = {
        key
        for a in actors
        if str(a.get("id", "")).startswith(ADMIN)
        and (key := _uuid(str(a["id"])[len(ADMIN) :])) is not None
    }
    agents = {
        key
        for a in actors
        if a.get("kind") == "agent" and (key := _uuid(str(a.get("id")))) is not None
    }
    out: dict[str, str] = {}
    if readers:
        rows = await session.execute(select(Reader.id, Reader.email).where(Reader.id.in_(readers)))
        out.update({f"{ADMIN}{rid}": email for rid, email in rows})
    if agents:
        rows = await session.execute(
            select(Agent.id, Agent.display_name).where(Agent.id.in_(agents))
        )
        out.update({str(aid): name for aid, name in rows})
    return out


def _label(actor: dict[str, Any], names: dict[str, str]) -> str:
    ident = str(actor.get("id", ""))
    if ident == "operator":
        return "操作者權杖"
    if ident in names:
        return names[ident]
    if actor.get("kind") == "system":
        return f"系統（{ident}）"
    return ident or "—"


@router.get("")
async def activity(
    session: Session,
    _: Operator,
    target_type: Target,
    target_id: uuid.UUID,
    limit: Annotated[int, Query(ge=1, le=MAX)] = 100,
) -> list[ActivityEntry]:
    subjects: list[tuple[str, uuid.UUID]] = [(target_type, target_id)]
    entries: list[ActivityEntry] = []

    if target_type == "article":
        asked = (
            await session.scalars(
                select(Approval).where(Approval.payload["article_id"].astext == str(target_id))
            )
        ).all()
        for approval in asked:
            subjects.append(("approval", approval.id))
            entries.append(
                ActivityEntry(
                    at=approval.created_at,
                    kind="asked",
                    subject="approval",
                    subject_id=str(approval.id),
                    actor=approval.requested_by,
                    actor_label="",
                    to_state="PENDING",
                    reason=approval.summary,
                )
            )
    elif target_type == "approval":
        approval = await session.get(Approval, target_id)
        if approval is not None:
            entries.append(
                ActivityEntry(
                    at=approval.created_at,
                    kind="asked",
                    subject="approval",
                    subject_id=str(approval.id),
                    actor=approval.requested_by,
                    actor_label="",
                    to_state="PENDING",
                    reason=approval.summary,
                )
            )

    for kind, ident in subjects:
        transitions = await session.scalars(
            select(StateTransition)
            .where(StateTransition.entity_type == kind, StateTransition.entity_id == ident)
            .order_by(StateTransition.at.desc())
            .limit(limit)
        )
        entries += [
            ActivityEntry(
                at=t.at,
                kind="state",
                subject=kind,
                subject_id=str(ident),
                actor=t.actor,
                actor_label="",
                from_state=t.from_state,
                to_state=t.to_state,
                reason=t.reason,
            )
            for t in transitions
        ]

    # what people did to the target itself; a decision on one of its approvals is already its
    # state change above, with who decided and why
    actions = await session.scalars(
        select(AdminAction)
        .where(AdminAction.target_type == target_type, AdminAction.target_id == str(target_id))
        .order_by(AdminAction.created_at.desc())
        .limit(limit)
    )
    entries += [
        ActivityEntry(
            at=a.created_at,
            kind="action",
            subject=target_type,
            subject_id=str(target_id),
            actor=a.actor,
            actor_label="",
            route=a.route,
            action=a.action,
            status=a.status,
            reason=(a.input.get("body") or {}).get("reason")
            if isinstance(a.input.get("body"), dict)
            else None,
        )
        for a in actions
    ]

    entries.sort(key=lambda e: e.at, reverse=True)
    entries = entries[:limit]
    names = await _labels(session, [e.actor for e in entries])
    return [e.model_copy(update={"actor_label": _label(e.actor, names)}) for e in entries]
