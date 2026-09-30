"""A newsroom that has gone quiet is told to the team group the same day (D-131).

The desk stopped three times in four days in 2026-09 — the CEO paused it, an approval expired
with nobody able to decide it — and each time the first sign was an empty front page a day
later. An hourly check now looks at one number, hours since the last article was published,
and when it passes a day says so in the team group, once a day, with what the records show
might be why: the business or the project paused, a desk member paused, articles waiting for
the operator's approval, runs failing, or simply no work started.

It decides nothing and changes nothing: no model, no command. It only makes a stopped newsroom
visible before a reader notices.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from autora.db.models import (
    Agent,
    AgentStatus,
    Approval,
    ApprovalState,
    BusinessUnit,
    BusinessUnitState,
    EventRecord,
    Project,
    ProjectState,
    WorkflowRun,
    WorkflowRunState,
)
from autora.domains.newsroom.events import NewsroomQuiet
from autora.domains.newsroom.models import Article
from autora.domains.newsroom.organization import BUSINESS_UNIT
from autora.runtime.actor import Actor
from autora.runtime.events.outbox import emit
from autora.runtime.events.schema import new_event

WATCH_SCHEDULE = "newsroom.watch_output"
WATCH_CRON = "25 * * * *"
QUIET = timedelta(hours=24)
"""A day without an article: the desk publishes daily, so a day is a missed day."""
DESK_ROLES = ("editor_in_chief", "writer", "editor", "researcher", "analyst")


async def quiet_newsroom(
    session: AsyncSession, company_id: uuid.UUID, *, now: datetime | None = None
) -> NewsroomQuiet | None:
    """What to say if the newsroom has been quiet for a day and it has not been said today."""
    now = now or datetime.now(UTC)
    unit = await session.scalar(
        select(BusinessUnit).where(
            BusinessUnit.company_id == company_id, BusinessUnit.key == BUSINESS_UNIT
        )
    )
    if unit is None:
        return None  # no newsroom here
    last = await session.scalar(
        select(func.max(Article.published_at)).where(Article.company_id == company_id)
    )
    since = last or unit.created_at
    if since is None or now - since < QUIET:
        return None
    said = await session.scalar(
        select(EventRecord.id)
        .where(
            EventRecord.company_id == company_id,
            EventRecord.event_type == "NEWSROOM_QUIET",
            EventRecord.occurred_at > now - QUIET,
        )
        .limit(1)
    )
    if said is not None:
        return None  # once a day

    causes: list[str] = []
    if unit.state != BusinessUnitState.ACTIVE.value:
        causes.append("business_paused")
    projects = (
        await session.scalars(select(Project).where(Project.business_unit_id == unit.id))
    ).all()
    if projects and not any(p.state == ProjectState.ACTIVE.value for p in projects):
        causes.append("project_paused")
    paused = await session.scalar(
        select(func.count())
        .select_from(Agent)
        .where(
            Agent.company_id == company_id,
            Agent.role.in_(DESK_ROLES),
            Agent.status == AgentStatus.PAUSED.value,
        )
    )
    if paused:
        causes.append("agent_paused")
    waiting = int(
        await session.scalar(
            select(func.count())
            .select_from(Approval)
            .where(
                Approval.company_id == company_id,
                Approval.kind == "article",
                Approval.state == ApprovalState.PENDING.value,
            )
        )
        or 0
    )
    if waiting:
        causes.append("awaiting_approval")
    project_ids = [p.id for p in projects]
    runs = (
        (
            await session.execute(
                select(WorkflowRun.state, func.count())
                .where(
                    WorkflowRun.project_id.in_(project_ids),
                    WorkflowRun.created_at > now - QUIET,
                )
                .group_by(WorkflowRun.state)
            )
        ).all()
        if project_ids
        else []
    )
    counted = {state: int(count) for state, count in runs}
    if counted.get(WorkflowRunState.FAILED.value):
        causes.append("runs_failed")
    if not counted:
        causes.append("no_work_started")
    return NewsroomQuiet(
        hours=int((now - since).total_seconds() // 3600),
        last_published_at=last,
        causes=causes,
        waiting_approvals=waiting,
    )


def schedule_handler():
    async def handler(session: AsyncSession, schedule, scheduled_for: datetime) -> None:
        quiet = await quiet_newsroom(session, schedule.company_id)
        if quiet is None:
            return
        await emit(
            session,
            new_event(
                quiet,
                company_id=schedule.company_id,
                actor=Actor.system("newsroom"),
                aggregate_type="company",
                aggregate_id=schedule.company_id,
            ),
        )

    return handler
