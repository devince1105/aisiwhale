"""The company's projects, as an operator sees and stops or restarts them (D-056).

The CEO pauses a project in its daily review (cycle 5 paused the newsroom's only one, for money
it thought the company did not have); until now only a script could start it again. Here both
directions go through the command bus — ``PauseProject`` / ``ResumeProject``, the same verbs the
CEO uses, under the same policy and in the same log — and a paused project says who paused it
and why, so a person can judge the decision before undoing it.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from autora.db.models import Company, Cycle, EventRecord, Project
from autora_api.deps import Operator, RuntimeDep, Session

router = APIRouter(prefix="/api/companies/{company_id}/projects", tags=["projects"])


class ProjectOut(BaseModel):
    id: uuid.UUID
    name: str
    state: str
    paused_at: datetime | None = None
    paused_by: str | None = None
    """``ceo``, ``human`` or ``kill_criteria``, as the pause recorded it."""
    pause_reason: str | None = None
    """The pause's own reason, or else the CEO's rationale for it in that cycle's review."""


class Decide(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


class DecisionOut(BaseModel):
    decision: str
    outcome: str | None
    reason: str | None
    state: str


async def _company(session: Session, company_id: uuid.UUID) -> None:
    if await session.get(Company, company_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"company {company_id} not found")


async def _ceo_rationale(session: Session, company_id: uuid.UUID, project_id: uuid.UUID) -> str:
    """What the CEO wrote about pausing it, in the latest review that did."""
    for review in await session.scalars(
        select(Cycle.review)
        .where(Cycle.company_id == company_id, Cycle.review.is_not(None))
        .order_by(Cycle.seq.desc())
        .limit(5)
    ):
        for line in (review or {}).get("projects") or []:
            if line.get("project_id") == str(project_id) and line.get("decision") == "pause":
                return str(line.get("rationale") or "")
    return ""


@router.get("")
async def list_projects(
    company_id: uuid.UUID, session: Session, operator: Operator
) -> list[ProjectOut]:
    await _company(session, company_id)
    out = []
    for project in await session.scalars(
        select(Project).where(Project.company_id == company_id).order_by(Project.created_at)
    ):
        line = ProjectOut(id=project.id, name=project.name, state=project.state)
        if project.state == "PAUSED":
            paused = await session.scalar(
                select(EventRecord)
                .where(
                    EventRecord.aggregate_id == project.id,
                    EventRecord.event_type == "PROJECT_PAUSED",
                )
                .order_by(EventRecord.seq.desc())
                .limit(1)
            )
            if paused is not None:
                line.paused_at = paused.occurred_at
                line.paused_by = (paused.payload or {}).get("trigger")
                line.pause_reason = (paused.payload or {}).get("reason") or None
                if line.pause_reason is None and line.paused_by == "ceo":
                    line.pause_reason = (
                        await _ceo_rationale(session, company_id, project.id) or None
                    )
        out.append(line)
    return out


async def _decide(
    session: Session,
    runtime: RuntimeDep,
    operator: Operator,
    company_id: uuid.UUID,
    project_id: uuid.UUID,
    verb: Literal["PauseProject", "ResumeProject"],
    reason: str | None,
) -> DecisionOut:
    await _company(session, company_id)
    project = await session.get(Project, project_id)
    if project is None or project.company_id != company_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"project {project_id} not found")
    result = await runtime.commands.submit(
        session,
        verb,
        {"project_id": str(project_id), "reason": reason},
        company_id=company_id,
        actor=operator,
        idempotency_key=f"{verb}:{project_id}:{uuid.uuid4().hex[:8]}",
    )
    await session.commit()
    await session.refresh(project)
    record = result.record
    return DecisionOut(
        decision=record.decision, outcome=record.outcome, reason=record.reason, state=project.state
    )


@router.post("/{project_id}/pause")
async def pause(
    company_id: uuid.UUID,
    project_id: uuid.UUID,
    body: Decide,
    session: Session,
    operator: Operator,
    runtime: RuntimeDep,
) -> DecisionOut:
    return await _decide(
        session, runtime, operator, company_id, project_id, "PauseProject", body.reason
    )


@router.post("/{project_id}/resume")
async def resume(
    company_id: uuid.UUID,
    project_id: uuid.UUID,
    body: Decide,
    session: Session,
    operator: Operator,
    runtime: RuntimeDep,
) -> DecisionOut:
    return await _decide(
        session, runtime, operator, company_id, project_id, "ResumeProject", body.reason
    )
