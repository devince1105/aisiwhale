"""D-260: the weekly meeting, where the strategy and what to stop are settled once a week.

What is held here:
- between meetings the CEO cannot pause, end or change the strategy, nor ask a person for it:
  she puts it on the agenda, and the same request asked daily is one item, asked N times;
- the meeting is held once a week (Taipei), inside EXECUTING, on the operations project; a seat
  nobody holds is left out, a failed meeting is held again, and without a CEO nobody meets;
- the minutes adopt a changed strategy at once, put every pause or end on one card for a person,
  and close the agenda they discussed; a rewording changes nothing;
- the CEO's snapshot shows what waits for the meeting and what a person said no to on its card.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from autora.app import build_policy_engine
from autora.company import verbs
from autora.company.agents.roster import hire_agent
from autora.company.commands import CommandBus
from autora.company.events import MeetingItemProposed
from autora.company.meeting import (
    APPLY,
    CHAIR,
    TAIPEI,
    TEMPLATE,
    Minutes,
    WeeklyMeeting,
    agenda,
    apply_step,
    build_template,
    statement_task,
    week_start,
)
from autora.company.reporting import Reporting
from autora.company.snapshot import STRATEGY_POLICY, SnapshotBuilder
from autora.db.models import (
    Approval,
    ApprovalState,
    CommandOutcome,
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
from autora.runtime.actor import Actor
from autora.runtime.approvals import ApprovalService
from autora.runtime.dag import TemplateRegistry, WorkflowEngine
from autora.runtime.events.outbox import emit
from autora.runtime.events.schema import new_event
from autora.runtime.services import ServiceContext
from autora.runtime.task_manager import TaskManager
from tests.conftest import unique_company

HUMAN = Actor.human("founder")
CEO = Actor.agent(uuid.uuid4())
ATTENDEES = ("writer", "editor", "marketing")


class World:
    def __init__(self):
        self.task_manager = TaskManager()
        templates = TemplateRegistry()
        templates.register(build_template(ATTENDEES))
        self.workflows = WorkflowEngine(self.task_manager, templates)
        self.approvals = ApprovalService(self.task_manager)
        self.bus = CommandBus(policy=build_policy_engine(), approvals=self.approvals)
        verbs.register(self.bus)
        self.bus.install()
        self.meeting = WeeklyMeeting(self.workflows, ATTENDEES)


async def _company(session, *roles):
    company = await unique_company(session, "meeting")
    for role in roles:
        await hire_agent(
            session, company_id=company.id, role=role, display_name=role.title(), actor=HUMAN
        )
    return company


async def _project(session, company, name="Newsroom") -> Project:
    project = Project(
        company_id=company.id, name=name, state=ProjectState.ACTIVE.value,
        kill_criteria={"note": "test"},
    )  # fmt: skip
    session.add(project)
    await session.flush()
    return project


async def _cycle(session, company, seq, started_at) -> Cycle:
    cycle = Cycle(
        company_id=company.id, seq=seq, stage=CycleStage.EXECUTING.value, started_at=started_at
    )
    session.add(cycle)
    await session.flush()
    return cycle


async def _meetings(session, company) -> list[WorkflowRun]:
    return list(
        (
            await session.scalars(
                select(WorkflowRun)
                .where(WorkflowRun.company_id == company.id, WorkflowRun.template_name == TEMPLATE)
                .order_by(WorkflowRun.created_at)
            )
        ).all()
    )


async def _propose(session, company, kind, proposal, project=None, *, hours_ago=2):
    """An agenda item asked before the meeting starts. The meeting's own start is the database's
    transaction time, so a test that proposes in the same transaction dates its items back."""
    await emit(
        session,
        new_event(
            MeetingItemProposed(
                kind=kind,
                proposal=proposal,
                project_id=project.id if project else None,
                project_name=project.name if project else None,
            ),
            company_id=company.id,
            actor=CEO,
            aggregate_type="company",
            aggregate_id=company.id,
            occurred_at=datetime.now(UTC) - timedelta(hours=hours_ago),
        ),
    )


# --- between meetings ---------------------------------------------------------------------------


async def test_the_ceo_puts_it_on_the_agenda_instead_of_asking_a_person(db_session):
    world = World()
    company = await _company(db_session, "ceo")
    project = await _project(db_session, company)

    async def submit(name, payload, key):
        return await world.bus.submit(
            db_session, name, payload, company_id=company.id, actor=CEO, role="ceo",
            idempotency_key=f"{key}-{uuid.uuid4().hex[:6]}",
        )  # fmt: skip

    for name, payload in (
        ("PauseProject", {"project_id": str(project.id), "reason": "no output"}),
        ("KillProject", {"project_id": str(project.id), "reason": "no output"}),
        ("UpdateStrategy", {"summary": "something else"}),
    ):
        result = await submit(name, payload, name)
        assert result.record.outcome == CommandOutcome.REFUSED.value, name
        assert result.approval is None, f"{name} must not reach a person"

    asked = await submit(
        "ProposeForMeeting",
        {"kind": "pause", "proposal": "零產出", "project_id": str(project.id)},
        "propose",
    )
    assert asked.done and asked.approval is None
    nameless = await submit("ProposeForMeeting", {"kind": "kill", "proposal": "x"}, "nameless")
    assert nameless.record.outcome == CommandOutcome.REFUSED.value
    assert "project_id" in (nameless.record.reason or "")
    pending = await db_session.scalar(
        select(Approval).where(
            Approval.company_id == company.id, Approval.state == ApprovalState.PENDING.value
        )
    )
    assert pending is None


async def test_the_same_request_asked_daily_is_one_item(db_session):
    company = await _company(db_session, "ceo")
    project = await _project(db_session, company)
    for day in (3, 2, 1):
        await _propose(db_session, company, "pause", f"day {day}", project, hours_ago=24 * day)
    await _propose(db_session, company, "strategy", "first", hours_ago=30)
    await _propose(db_session, company, "strategy", "second", hours_ago=5)
    await _propose(db_session, company, "other", "hire a designer", hours_ago=4)

    items = await agenda(db_session, company.id)
    by_kind = {item.kind: item for item in items}
    assert len(items) == 3
    assert (by_kind["pause"].times, by_kind["pause"].proposal) == (3, "day 1")
    assert (by_kind["strategy"].times, by_kind["strategy"].proposal) == (2, "second")
    assert "提了 3 次" in by_kind["pause"].line() and "Newsroom" in by_kind["pause"].line()


# --- when it meets ------------------------------------------------------------------------------


def test_a_week_starts_on_monday_in_taipei():
    # Sunday 23:30 in Taipei is still last week; Monday 00:10 is the new one
    sunday = datetime(2026, 11, 1, 23, 30, tzinfo=TAIPEI)
    monday = datetime(2026, 11, 2, 0, 10, tzinfo=TAIPEI)
    assert week_start(sunday) == datetime(2026, 10, 26, tzinfo=TAIPEI)
    assert week_start(monday) == datetime(2026, 11, 2, tzinfo=TAIPEI)
    # given in UTC: Monday 01:00 Taipei is Sunday 17:00 UTC
    assert week_start(monday.astimezone(UTC)) == datetime(2026, 11, 2, tzinfo=TAIPEI)


async def test_it_meets_once_a_week_and_leaves_empty_seats_out(db_session):
    """Workflow runs are stamped by the database clock, so the cycles are placed around now."""
    world = World()
    company = await _company(db_session, "ceo", "writer", "editor")  # nobody in marketing
    now = datetime.now(UTC)
    first = await _cycle(db_session, company, 1, now)
    await world.meeting.stage_hook()(db_session, first)
    await world.meeting.stage_hook()(db_session, first)  # the stage entered twice: one meeting
    [meeting] = await _meetings(db_session, company)

    tasks = {
        t.name: t
        for t in await db_session.scalars(select(Task).where(Task.workflow_run_id == meeting.id))
    }
    seats = {statement_task("writer"), statement_task("editor")}
    assert set(tasks) == seats | {CHAIR, "apply_minutes"}
    assert set(tasks[CHAIR].depends_on) == {
        tasks[statement_task("writer")].id,
        tasks[statement_task("editor")].id,
    }, "the chair waits for the members present, and for nobody else"
    assert tasks["apply_minutes"].input["service"] == APPLY
    project = await db_session.get(Project, meeting.project_id)
    assert project.name == "Company operations"

    later = await _cycle(db_session, company, 2, now + timedelta(minutes=1))
    await world.meeting.stage_hook()(db_session, later)
    assert len(await _meetings(db_session, company)) == 1, "the same week: not again"

    next_week = await _cycle(db_session, company, 3, now + timedelta(days=7))
    await world.meeting.stage_hook()(db_session, next_week)
    assert len(await _meetings(db_session, company)) == 2


async def test_a_failed_meeting_is_held_again_and_nobody_meets_without_a_ceo(db_session):
    world = World()
    company = await _company(db_session, "ceo", "writer")
    now = datetime.now(UTC)
    await world.meeting.stage_hook()(db_session, await _cycle(db_session, company, 1, now))
    [meeting] = await _meetings(db_session, company)
    meeting.state = WorkflowRunState.FAILED.value
    await db_session.flush()
    await world.meeting.stage_hook()(
        db_session, await _cycle(db_session, company, 2, now + timedelta(minutes=1))
    )
    assert len(await _meetings(db_session, company)) == 2

    chairless = await _company(db_session, "writer", "editor")
    await world.meeting.stage_hook()(db_session, await _cycle(db_session, chairless, 1, now))
    assert await _meetings(db_session, chairless) == []


# --- what it decides ----------------------------------------------------------------------------


async def _held(world, session, company, minutes: Minutes):
    """Hold this week's meeting: the members speak, the chair writes ``minutes``, apply runs."""
    await world.meeting.stage_hook()(session, await _cycle(session, company, 1, datetime.now(UTC)))
    [meeting] = await _meetings(session, company)
    tasks = {
        t.name: t
        for t in await session.scalars(select(Task).where(Task.workflow_run_id == meeting.id))
    }
    for name, task in tasks.items():
        if name.startswith("statement_"):
            await world.task_manager.complete_without_run(
                session, task, {"done": ["寫了兩篇"], "blockers": [], "asks": [], "on_agenda": []}
            )
    await session.refresh(tasks[CHAIR])
    await world.task_manager.complete_without_run(
        session, tasks[CHAIR], minutes.model_dump(mode="json")
    )
    apply = tasks["apply_minutes"]
    await session.refresh(apply)
    await apply_step(world.bus)(
        ServiceContext(
            session=session, task=apply, task_manager=world.task_manager,
            approvals=world.approvals, policy=world.bus.policy, actor=Actor.system("services"),
        )
    )  # fmt: skip
    await session.refresh(meeting)
    return meeting


async def test_the_minutes_adopt_the_strategy_and_ask_for_every_stop_on_one_card(db_session):
    world = World()
    company = await _company(db_session, "ceo", "writer", "editor", "marketing")
    newsroom = await _project(db_session, company, "Newsroom")
    lab = await _project(db_session, company, "Lab")
    await _propose(db_session, company, "pause", "零產出", newsroom)
    await _propose(db_session, company, "strategy", "專注台股")

    meeting = await _held(
        world,
        db_session,
        company,
        Minutes(
            summary="這週零產出；改策略，暫停新聞室、結束實驗室。",
            decisions=["改策略", "暫停新聞室", "結束實驗室"],
            strategy="專注台股公司公告，每天兩篇。",
            stop=[
                {"project_id": newsroom.id, "action": "pause", "reason": "七天零篇"},
                {"project_id": lab.id, "action": "kill", "reason": "三週沒有產出"},
            ],
        ),
    )
    assert meeting.state == WorkflowRunState.SUCCEEDED.value

    policies = await company_repo.get_policies(db_session, company.id)
    assert policies[STRATEGY_POLICY] == "專注台股公司公告，每天兩篇。", "adopted without a person"

    [card] = (
        await db_session.scalars(
            select(Approval).where(
                Approval.company_id == company.id, Approval.state == ApprovalState.PENDING.value
            )
        )
    ).all()
    assert card.payload["command"] == "ApplyMeetingDecisions"
    assert [i["action"] for i in card.payload["args"]["items"]] == ["pause", "kill"]
    assert card.expires_at - card.created_at > timedelta(days=5), "waits until the next meeting"
    assert (await db_session.get(Project, newsroom.id)).state == ProjectState.ACTIVE.value

    held = await db_session.scalar(
        select(EventRecord).where(
            EventRecord.company_id == company.id, EventRecord.event_type == "MEETING_HELD"
        )
    )
    assert held.payload["strategy"] == "專注台股公司公告，每天兩篇。"
    assert held.payload["stop_requests"] == 2
    assert set(held.payload["attendees"]) == {"writer", "editor", "marketing"}
    assert await agenda(db_session, company.id) == [], "what it discussed is off the agenda"

    # the person approves; the lab was ended meanwhile, which skips it and pauses the newsroom
    (await db_session.get(Project, lab.id)).state = ProjectState.KILLED.value
    await db_session.flush()
    await world.approvals.decide(db_session, card.id, outcome="approve", actor=HUMAN)
    assert (await db_session.get(Project, newsroom.id)).state == ProjectState.PAUSED.value


async def test_a_reworded_strategy_and_nothing_to_stop_ask_nobody_anything(db_session):
    world = World()
    company = await _company(db_session, "ceo", "writer")
    await company_repo.upsert_policy(
        db_session, company.id, STRATEGY_POLICY, "專注台股。", updated_by=HUMAN.as_json()
    )
    await _held(
        world,
        db_session,
        company,
        Minutes(summary="照常。", strategy=" 專注台股。 "),
    )
    commands = (
        await db_session.scalars(
            select(EventRecord.event_type).where(
                EventRecord.company_id == company.id,
                EventRecord.event_type.in_(("STRATEGY_UPDATED", "APPROVAL_REQUESTED")),
            )
        )
    ).all()
    assert commands == []


async def test_the_ceo_sees_the_agenda_and_a_no_on_the_meetings_card(db_session):
    world = World()
    company = await _company(db_session, "ceo", "writer")
    newsroom = await _project(db_session, company, "Newsroom")
    await _held(
        world,
        db_session,
        company,
        Minutes(
            summary="暫停新聞室。",
            stop=[{"project_id": newsroom.id, "action": "pause", "reason": "零產出"}],
        ),
    )
    card = await db_session.scalar(
        select(Approval).where(
            Approval.company_id == company.id, Approval.state == ApprovalState.PENDING.value
        )
    )
    await world.approvals.decide(
        db_session, card.id, outcome="reject", actor=HUMAN, reason="金鑰已修好"
    )
    await _propose(db_session, company, "other", "補一位設計", hours_ago=0)

    snapshot = await SnapshotBuilder(Reporting()).build(db_session, company.id)
    assert snapshot.meeting is not None
    assert snapshot.meeting.last_summary == "暫停新聞室。"
    assert snapshot.meeting.agenda == ["其他：補一位設計"]
    [line] = [p for p in snapshot.company_work if p.id == newsroom.id]
    assert [(d.decision, d.reason) for d in line.operator_decisions] == [
        ("rejected_pause", "金鑰已修好")
    ]
