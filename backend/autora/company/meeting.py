"""The weekly meeting (D-260): the staff talk the week over, and what used to be a request to a
person every day is settled there once a week.

Before it, the CEO asked a person for every new strategy and every pause or end she wanted —
thirteen requests in two weeks, eleven of them left to lapse unread, and the same ones asked
again the next day. Now she puts them on the meeting's agenda (``ProposeForMeeting``), and the
meeting is where they are decided:

    first cycle of a week (Taipei), EXECUTING entered
      -> instantiate company.weekly_meeting_v1, on the company's operations project
      -> every member who holds a seat speaks (in parallel): the week, what is stuck, the agenda
      -> the CEO chairs: the minutes, the strategy, what to stop
      -> apply (a service step, as the system): a changed strategy is adopted at once; every
         pause or end goes to a person together, on one card; the minutes go to the team group

**Once a week, inside the daily cycle**, like the market watch: the cycle is the only root that
starts agent work. The first cycle on or after Monday holds it; a meeting that failed does not
count, so the next day's cycle holds it instead. EXECUTING waits for it like for any work its
cycle started.

**A seat nobody holds is left out** (``omit``), not waited for: a company that has not hired a
marketer meets without one. A company with no CEO has nobody to chair and does not meet.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from autora.company.agents.ceo import ROLE as CEO_ROLE
from autora.company.commands import CommandBus
from autora.company.events import MeetingHeld
from autora.company.executive import operations_project
from autora.company.snapshot import MeetingLine
from autora.company.verbs import StopRequest
from autora.db.models import (
    Agent,
    AgentRun,
    AgentRunState,
    AgentStatus,
    Cycle,
    CycleStage,
    EventRecord,
    Project,
    ProjectState,
    Task,
    WorkflowRun,
    WorkflowRunState,
)
from autora.db.repositories import companies as company_repo
from autora.infra.money import format_money, fx
from autora.runtime.actor import Actor
from autora.runtime.behaviors import AgentBehavior, BehaviorRegistry, RunContext
from autora.runtime.dag import NodeSpec, TemplateRegistry, WorkflowEngine, WorkflowTemplate
from autora.runtime.events.outbox import emit
from autora.runtime.events.schema import new_event
from autora.runtime.services import ServiceContext

log = logging.getLogger(__name__)

TEMPLATE = "company.weekly_meeting_v1"
CHAIR = "chair_meeting"
APPLY = "company.apply_meeting"
ROLE = "system"
"""What the apply step acts as: code applying the minutes, so the policy's "system" — which may
adopt a strategy, and must ask a person for any pause or end on the meeting's card
(``company/policy.py``)."""
ACTOR = Actor.system("weekly-meeting")
TAIPEI = ZoneInfo("Asia/Taipei")
WEEK = timedelta(days=7)
AGENDA_OTHERS = 10
"""At most this many "other" items: the newest. Strategy, pause and end keep one item each (per
project), the latest — the same request made daily is one item, asked N times."""


def statement_task(role: str) -> str:
    return f"statement_{role}"


def build_template(attendees: tuple[str, ...]) -> WorkflowTemplate:
    """One seat per role that may attend, the chair after all of them, then the apply step."""
    seats = tuple(
        NodeSpec(statement_task(role), "週會發言（第 {seq} 期）", role, max_attempts=2)
        for role in attendees
    )
    return WorkflowTemplate(
        name=TEMPLATE,
        nodes=(
            *seats,
            NodeSpec(
                CHAIR,
                "主持週會（第 {seq} 期）",
                CEO_ROLE,
                depends_on=tuple(seat.name for seat in seats),
            ),
            NodeSpec("apply_minutes", "套用週會決議", "system", depends_on=(CHAIR,), service=APPLY),
        ),
    )


def register_templates(templates: TemplateRegistry, attendees: tuple[str, ...]) -> None:
    templates.register(build_template(attendees))


# --- the agenda --------------------------------------------------------------------------------


class AgendaItem(BaseModel):
    kind: Literal["strategy", "pause", "kill", "other"]
    proposal: str
    project_id: uuid.UUID | None = None
    project_name: str | None = None
    proposed_at: datetime
    times: int = 1
    """How many times it was asked between meetings; the text is the latest asking's."""

    def line(self) -> str:
        what = {"strategy": "改策略", "pause": "暫停專案", "kill": "終止專案", "other": "其他"}
        head = what[self.kind] + (f"「{self.project_name}」" if self.project_name else "")
        again = f"（提了 {self.times} 次）" if self.times > 1 else ""
        return f"{head}{again}：{self.proposal}"


async def last_meeting(session: AsyncSession, company_id: uuid.UUID) -> EventRecord | None:
    return await session.scalar(
        select(EventRecord)
        .where(EventRecord.company_id == company_id, EventRecord.event_type == "MEETING_HELD")
        .order_by(EventRecord.seq.desc())
        .limit(1)
    )


async def agenda(
    session: AsyncSession, company_id: uuid.UUID, *, until: datetime | None = None
) -> list[AgendaItem]:
    """What waits for the meeting: proposed after the last meeting closed its agenda, and before
    ``until`` (this meeting's start) when given."""
    held = await last_meeting(session, company_id)
    since = None
    if held is not None:
        since = datetime.fromisoformat(str(held.payload["agenda_until"]))
    query = select(EventRecord).where(
        EventRecord.company_id == company_id, EventRecord.event_type == "MEETING_ITEM_PROPOSED"
    )
    if since is not None:
        query = query.where(EventRecord.occurred_at > since)
    if until is not None:
        query = query.where(EventRecord.occurred_at <= until)
    kept: dict[tuple[str, str], AgendaItem] = {}
    others: list[AgendaItem] = []
    for event in await session.scalars(query.order_by(EventRecord.seq)):
        payload = event.payload or {}
        item = AgendaItem(
            kind=payload["kind"],
            proposal=payload["proposal"],
            project_id=payload.get("project_id"),
            project_name=payload.get("project_name"),
            proposed_at=event.occurred_at,
        )
        if item.kind == "other":
            others.append(item)
            continue
        key = (item.kind, str(item.project_id or ""))
        if key in kept:
            item.times = kept[key].times + 1
        kept[key] = item
    items = list(kept.values()) + others[-AGENDA_OTHERS:]
    return sorted(items, key=lambda item: item.proposed_at)


def agenda_text(items: list[AgendaItem]) -> str:
    if not items:
        return "議程：這週沒有人提案。"
    return "議程：\n" + "\n".join(f"{n}. {item.line()}" for n, item in enumerate(items, 1))


# --- what the members say ----------------------------------------------------------------------


class AgendaView(BaseModel):
    item: int = Field(ge=1)
    view: Literal["support", "oppose", "neutral"]
    why: str = Field(min_length=1, max_length=200)


class Statement(BaseModel):
    """One member's turn: the week from their desk, and where they stand on the agenda."""

    done: list[str] = Field(default_factory=list, max_length=3)
    blockers: list[str] = Field(default_factory=list, max_length=3)
    asks: list[str] = Field(default_factory=list, max_length=2)
    on_agenda: list[AgendaView] = Field(default_factory=list, max_length=8)


STATEMENT_PROMPT = """You are a member of an autonomous company's staff, at its weekly meeting.
It is your turn to speak. You are given who you are, what your own runs did in the last seven
days, the company's strategy, and the meeting's agenda.

Say, in Traditional Chinese as written in Taiwan, briefly:
- done: up to three things you got done this week, from your runs — never invented;
- blockers: up to three things that stopped or slowed you, from your failures; none is fine;
- asks: up to two things you need from the others or from the CEO;
- on_agenda: for the agenda items your work gives you a view on, support, oppose or neutral,
  with one sentence why. Leave out items your work says nothing about.

Speak only from what you are given. Each line is one short sentence."""


async def _meeting_run(session: AsyncSession, task: Task) -> WorkflowRun | None:
    if task.workflow_run_id is None:
        return None
    return await session.get(WorkflowRun, task.workflow_run_id)


async def _started(session: AsyncSession, ctx: RunContext) -> datetime:
    run = await _meeting_run(session, ctx.task)
    return run.created_at if run is not None else datetime.now(UTC)


async def _week_of(session: AsyncSession, agent: Agent, *, until: datetime) -> list[str]:
    """What this member's own runs did in the seven days before the meeting."""
    since = until - WEEK
    rows = (
        await session.execute(
            select(AgentRun.state, AgentRun.error, AgentRun.cost_usd, Task.display_name)
            .join(Task, Task.id == AgentRun.task_id)
            .where(
                AgentRun.agent_id == agent.id,
                AgentRun.created_at >= since,
                AgentRun.created_at < until,
            )
            .order_by(AgentRun.created_at.desc())
        )
    ).all()
    if not rows:
        return ["這七天你沒有任何執行紀錄。"]
    completed = [row for row in rows if row.state == AgentRunState.COMPLETED.value]
    failed = [row for row in rows if row.state == AgentRunState.FAILED.value]
    cost = sum((row.cost_usd or 0 for row in rows), 0)
    lines = [
        f"這七天你執行了 {len(rows)} 次：完成 {len(completed)} 次、失敗 {len(failed)} 次；"
        f"模型花費 {format_money(fx().metered(cost))}。"
    ]
    names = list(dict.fromkeys(row.display_name for row in completed))[:8]
    if names:
        lines.append("完成的工作（新的在前）：" + "；".join(names))
    for row in failed[:5]:
        error = row.error or {}
        why = str(error.get("message") or error.get("class") or "沒有記錄原因")[:160]
        lines.append(f"失敗：{row.display_name}（{why}）")
    return lines


async def statement_context(session: AsyncSession, ctx: RunContext) -> str:
    started = await _started(session, ctx)
    policies = await company_repo.get_policies(session, ctx.company_id)
    strategy = _text(policies.get("company.strategy_summary"))
    lines = [f"你是 {ctx.agent.display_name}，職務 {ctx.agent.role}。"]
    if ctx.agent.description:
        lines.append(ctx.agent.description)
    lines += await _week_of(session, ctx.agent, until=started)
    if strategy:
        lines.append(f"公司目前的策略：{strategy}")
    lines.append(agenda_text(await agenda(session, ctx.company_id, until=started)))
    return "\n".join(lines)


async def views_are_on_the_agenda(
    session: AsyncSession, ctx: RunContext, output: BaseModel
) -> list[str]:
    if not isinstance(output, Statement) or not output.on_agenda:
        return []
    count = len(await agenda(session, ctx.company_id, until=await _started(session, ctx)))
    return [
        f"agenda item {view.item} does not exist (the agenda has {count})"
        for view in output.on_agenda
        if view.item > count
    ]


# --- the chair ---------------------------------------------------------------------------------


class DiscussionPoint(BaseModel):
    speaker: str = Field(min_length=1, max_length=60)
    point: str = Field(min_length=1, max_length=300)


class ActionItem(BaseModel):
    owner: str = Field(min_length=1, max_length=60)
    item: str = Field(min_length=1, max_length=200)


class Minutes(BaseModel):
    """What the meeting concluded, as the CEO writes it up."""

    summary: str = Field(min_length=1, max_length=800)
    discussion: list[DiscussionPoint] = Field(default_factory=list, max_length=12)
    decisions: list[str] = Field(default_factory=list, max_length=8)
    action_items: list[ActionItem] = Field(default_factory=list, max_length=8)
    strategy: str | None = Field(default=None, max_length=1500)
    """The company's new strategy, when the meeting changes it. Adopted as written."""
    stop: list[StopRequest] = Field(default_factory=list, max_length=3)
    """Projects the meeting wants paused or ended. A person decides, on one card."""


CHAIR_PROMPT = """You are the chief executive of an autonomous company, chairing its weekly
meeting. Your staff have spoken; you are given what each said, the agenda, and the company's
snapshot. Write the minutes, in Traditional Chinese as written in Taiwan:

- summary: what the week came to and what the meeting decided, readable in ten seconds;
- discussion: who raised what — name the speaker as given;
- decisions: what the meeting decided, one line each. Every agenda item gets an answer, even
  if the answer is "not now, because ...";
- action_items: who does what by the next meeting;
- strategy: only when the meeting changes the company's strategy, the new strategy in full.
  It is adopted as written, without asking anyone, and you plan every day by it. Change it only
  for a reason you can name in this week's numbers or in what was said; a rewording is not a
  change — leave it null;
- stop: projects to pause or to end, each with the numbers that justify it. A person decides
  these, all on one card; until they do, the work goes on. The snapshot's operator_decisions
  are what a person already answered — do not ask again on the same grounds.

Use only what you are given. Do not invent numbers."""


async def chair_context(snapshots, session: AsyncSession, ctx: RunContext) -> str:
    started = await _started(session, ctx)
    lines = [agenda_text(await agenda(session, ctx.company_id, until=started)), "", "發言："]
    for name, statement in await _statements(session, ctx.task):
        lines.append(f"- {name}：")
        for label, key in (("完成", "done"), ("卡住", "blockers"), ("需要", "asks")):
            for text in statement.get(key) or []:
                lines.append(f"  {label}：{text}")
        for view in statement.get("on_agenda") or []:
            lines.append(f"  對議程第 {view.get('item')} 項 {view.get('view')}：{view.get('why')}")
    snapshot = await snapshots.build(session, ctx.company_id)
    lines += ["", "The company right now:", snapshot.model_dump_json(indent=2, exclude_none=True)]
    return "\n".join(lines)


async def _statements(session: AsyncSession, chair: Task) -> list[tuple[str, dict[str, Any]]]:
    """Who said what, in seat order: the speaker's name from the run that spoke."""
    if not chair.depends_on:
        return []
    seats = (
        await session.scalars(
            select(Task).where(Task.id.in_(chair.depends_on)).order_by(Task.created_at)
        )
    ).all()
    said = []
    for seat in seats:
        if not seat.output:
            continue
        name = await session.scalar(
            select(Agent.display_name)
            .join(AgentRun, AgentRun.agent_id == Agent.id)
            .where(AgentRun.task_id == seat.id, AgentRun.state == AgentRunState.COMPLETED.value)
            .order_by(AgentRun.finished_at.desc())
            .limit(1)
        )
        said.append((name or seat.required_role, seat.output))
    return said


async def stops_are_real(session: AsyncSession, ctx: RunContext, output: BaseModel) -> list[str]:
    if not isinstance(output, Minutes) or not output.stop:
        return []
    issues = []
    for request in output.stop:
        project = await session.get(Project, request.project_id)
        if project is None or project.company_id != ctx.company_id:
            issues.append(f"project {request.project_id} is not one of this company's")
        elif request.action == "pause" and project.state != ProjectState.ACTIVE.value:
            issues.append(f"{project.name} is {project.state}; only an ACTIVE project is paused")
        elif project.state in (ProjectState.KILLED.value, ProjectState.COMPLETED.value):
            issues.append(f"{project.name} is already {project.state}")
    return issues


def behaviors(snapshots, attendees: tuple[str, ...]) -> tuple[AgentBehavior, ...]:
    async def chair(session: AsyncSession, ctx: RunContext) -> str:
        return await chair_context(snapshots, session, ctx)

    seats = tuple(
        AgentBehavior(
            role=role,
            task_name=statement_task(role),
            capability="drafting",
            system_prompt=STATEMENT_PROMPT,
            output_model=Statement,
            validators=(views_are_on_the_agenda,),
            max_steps=3,
            repair_limit=1,
            max_output_tokens=1024,
            context=statement_context,
            summarize=_statement_summary,
        )
        for role in attendees
    )
    return (
        *seats,
        AgentBehavior(
            role=CEO_ROLE,
            task_name=CHAIR,
            capability="reasoning",
            system_prompt=CHAIR_PROMPT,
            output_model=Minutes,
            validators=(stops_are_real,),
            max_steps=3,
            repair_limit=2,
            max_output_tokens=4096,
            context=chair,
            summarize=lambda minutes: minutes.summary[:200],  # type: ignore[attr-defined]
        ),
    )


def register_behaviors(registry: BehaviorRegistry, snapshots, attendees: tuple[str, ...]) -> None:
    for behavior in behaviors(snapshots, attendees):
        registry.register(behavior)


def _statement_summary(statement: BaseModel) -> str:
    assert isinstance(statement, Statement)
    return (
        f"{len(statement.done)} done, {len(statement.blockers)} blocked, {len(statement.asks)} asks"
    )


# --- applying what it decided ------------------------------------------------------------------


def apply_step(commands: CommandBus):
    """The service step after the chair: adopt, ask, and tell the team group."""

    async def apply(ctx: ServiceContext) -> None:
        session, task = ctx.session, ctx.task
        chair = await session.scalar(select(Task).where(Task.id.in_(task.depends_on or [])))
        if chair is None or not chair.output:
            await ctx.fail("no_minutes", "the chair wrote no minutes")
            return
        minutes = Minutes.model_validate(chair.output)
        run = await session.get(WorkflowRun, task.workflow_run_id)
        assert run is not None
        company_id = task.company_id

        policies = await company_repo.get_policies(session, company_id)
        current = _text(policies.get("company.strategy_summary")) or ""
        adopted = None
        if minutes.strategy and minutes.strategy.strip() != current.strip():
            result = await commands.submit(
                session,
                "UpdateStrategy",
                {"summary": minutes.strategy.strip()},
                company_id=company_id,
                actor=ACTOR,
                role=ROLE,
                idempotency_key=f"meeting:{run.id}:strategy",
            )
            adopted = minutes.strategy.strip() if result.done else None
        card = None
        if minutes.stop:
            result = await commands.submit(
                session,
                "ApplyMeetingDecisions",
                {
                    "summary": minutes.summary,
                    "items": [item.model_dump(mode="json") for item in minutes.stop],
                },
                company_id=company_id,
                actor=ACTOR,
                role=ROLE,
                idempotency_key=f"meeting:{run.id}:stop",
            )
            card = result.approval

        attendees = [name for name, _ in await _statements(session, chair)]
        await emit(
            session,
            new_event(
                MeetingHeld(
                    workflow_run_id=run.id,
                    agenda_until=run.created_at,
                    attendees=attendees,
                    summary=minutes.summary,
                    decisions=minutes.decisions,
                    action_items=[f"{a.owner}：{a.item}" for a in minutes.action_items],
                    strategy=adopted,
                    stop_requests=len(minutes.stop) if card is not None else 0,
                ),
                company_id=company_id,
                actor=ACTOR,
                aggregate_type="workflow_run",
                aggregate_id=run.id,
                workflow_run_id=run.id,
                cycle_id=run.cycle_id,
            ),
        )
        await ctx.complete(
            {
                "strategy_adopted": adopted is not None,
                "stop_card": str(card.id) if card is not None else None,
                "attendees": attendees,
            },
            summary=minutes.summary[:200],
        )

    return apply


# --- when it meets -----------------------------------------------------------------------------


def week_start(moment: datetime) -> datetime:
    """Monday 00:00 in Taipei of the week ``moment`` falls in."""
    local = moment.astimezone(TAIPEI)
    monday = (local - timedelta(days=local.weekday())).date()
    return datetime(monday.year, monday.month, monday.day, tzinfo=TAIPEI)


class WeeklyMeeting:
    """Starts the week's meeting on entering EXECUTING. Owns no loop of its own."""

    def __init__(
        self, workflows: WorkflowEngine, attendees: tuple[str, ...], actor: Actor | None = None
    ):
        self.workflows = workflows
        self.attendees = attendees
        self.actor = actor or ACTOR

    def stage_hook(self):
        async def meet(session: AsyncSession, cycle: Cycle) -> None:
            await self.start(session, cycle)

        return meet

    def install(self, cycles) -> None:
        cycles.when_entering(CycleStage.EXECUTING, self.stage_hook())

    async def start(self, session: AsyncSession, cycle: Cycle) -> WorkflowRun | None:
        """Start this week's meeting, unless it was held or there is nobody to chair. No commit."""
        present = await self._present(session, cycle.company_id)
        if CEO_ROLE not in present:
            return None  # nobody to chair: a real state, and not an error
        if await self._held_this_week(session, cycle):
            return None  # once a week; and the stage may be entered twice
        project = await operations_project(session, cycle.company_id, actor=self.actor)
        if project.state != ProjectState.ACTIVE.value:
            log.info("company %s: operations is %s; no meeting", cycle.company_id, project.state)
            return None
        run, _ = await self.workflows.instantiate(
            session,
            TEMPLATE,
            company_id=cycle.company_id,
            project_id=project.id,
            params={"seq": cycle.seq},
            cycle_id=cycle.id,
            omit=frozenset(statement_task(r) for r in self.attendees if r not in present),
        )
        return run

    async def _held_this_week(self, session: AsyncSession, cycle: Cycle) -> bool:
        """A meeting started this week counts, unless it failed: an outage should not cost the
        company its week's meeting."""
        return (
            await session.scalar(
                select(func.count())
                .select_from(WorkflowRun)
                .where(
                    WorkflowRun.company_id == cycle.company_id,
                    WorkflowRun.template_name == TEMPLATE,
                    WorkflowRun.state.not_in(
                        (WorkflowRunState.FAILED.value, WorkflowRunState.CANCELLED.value)
                    ),
                    WorkflowRun.created_at >= week_start(cycle.started_at),
                )
            )
        ) > 0

    async def _present(self, session: AsyncSession, company_id: uuid.UUID) -> set[str]:
        return set(
            (
                await session.scalars(
                    select(Agent.role).where(
                        Agent.company_id == company_id,
                        Agent.status == AgentStatus.ACTIVE.value,
                    )
                )
            ).all()
        )


# --- what the CEO sees of it -------------------------------------------------------------------


async def snapshot_line(session: AsyncSession, company_id: uuid.UUID) -> MeetingLine:
    held = await last_meeting(session, company_id)
    line = MeetingLine(agenda=[item.line() for item in await agenda(session, company_id)])
    if held is not None:
        line.last_held = held.occurred_at
        line.last_summary = held.payload.get("summary")
        line.last_decisions = list(held.payload.get("decisions") or [])
    return line


def _text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None
