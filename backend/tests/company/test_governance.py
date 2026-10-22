"""T-606: the rules that run without asking anybody.

What matters here is that these hold when the CEO does not: they read numbers that already
exist, they never call a model, and a project whose own stated criteria are breached stops
whether or not anyone agrees.
"""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select

from autora.app import build_policy_engine
from autora.company import verbs
from autora.company.agents.roster import hire_agent
from autora.company.commands import CommandBus
from autora.company.governance import (
    FAILURES_BEFORE_PAUSE,
    WARN_AT,
    Governance,
)
from autora.company.organization import add_business_unit, bootstrap_executive, role_by_key
from autora.company.reporting import Reporting
from autora.db.models import (
    AgentRun,
    AgentStatus,
    Budget,
    BusinessUnit,
    BusinessUnitState,
    CommandRecord,
    Cycle,
    EventRecord,
    KpiScope,
    KpiSnapshot,
    ModelCall,
    Project,
    ProjectState,
    Task,
    WorkflowRun,
)
from autora.runtime.actor import Actor
from autora.runtime.approvals import ApprovalService
from autora.runtime.task_manager import TaskManager
from tests.conftest import unique_company

HUMAN = Actor.human("founder")
START = datetime(2026, 9, 21, 6, 0, tzinfo=UTC)
END = START + timedelta(hours=14)

PAUSE_IF = {"metric": "newsroom.cost_per_published_article", "op": ">", "value": 3.0}


def _governance() -> Governance:
    bus = CommandBus(policy=build_policy_engine(), approvals=ApprovalService(TaskManager()))
    verbs.register(bus)
    bus.install()
    return Governance(commands=bus)


async def _company(db_session, *, seq: int = 1, unit_criteria=None, project_criteria=None):
    company = await unique_company(db_session, "gov")
    unit = await add_business_unit(
        db_session, company_id=company.id, key="ai_media", name="AI Media",
        actor=HUMAN, state=BusinessUnitState.ACTIVE, kill_criteria=unit_criteria,
    )  # fmt: skip
    project = Project(
        company_id=company.id,
        business_unit_id=unit.id,
        name="Lumen Daily",
        state=ProjectState.ACTIVE.value,
        kill_criteria=project_criteria if project_criteria is not None else {"note": "none"},
    )
    # a cycle in REVIEWING has not ended: the database enforces "ended_at iff DONE" (T-601)
    cycle = Cycle(company_id=company.id, seq=seq, stage="REVIEWING", started_at=START)
    db_session.add_all([project, cycle])
    await db_session.flush()
    return company, unit, project, cycle


async def _measured(db_session, company, cycle, *, project=None, unit=None, **metrics):
    """A KPI snapshot with the numbers a rule will read."""
    snapshot = KpiSnapshot(
        company_id=company.id,
        cycle_id=cycle.id,
        project_id=project.id if project else None,
        business_unit_id=unit.id if unit else None,
        scope=(KpiScope.PROJECT if project else KpiScope.BUSINESS_UNIT).value
        if (project or unit)
        else KpiScope.COMPANY.value,
        metrics=metrics,
        period_start=cycle.started_at,
        period_end=cycle.ended_at or END,
    )
    db_session.add(snapshot)
    await db_session.flush()
    return snapshot


# --- 1. kill criteria ----------------------------------------------------------------------------


async def _stopped(db_session, company) -> list[str]:
    """Every pause and kill commanded or recorded in the company: none, since D-258."""
    commands = (
        await db_session.scalars(
            select(CommandRecord.command).where(
                CommandRecord.company_id == company.id,
                CommandRecord.command.in_(["PauseProject", "PauseAgent", "KillProject"]),
            )
        )
    ).all()
    events = (
        await db_session.scalars(
            select(EventRecord.event_type).where(
                EventRecord.company_id == company.id,
                EventRecord.event_type.in_(
                    ["PROJECT_PAUSED", "BUSINESS_UNIT_PAUSED", "AGENT_PAUSED"]
                ),
            )
        )
    ).all()
    return [*commands, *events]


async def test_a_project_that_breaks_its_own_criteria_is_reported_not_paused(db_session):
    """The number to beat was chosen before anyone knew whether it would be met — and since
    D-258 a breach is told, not acted on: a person decides whether the project stops."""
    company, unit, project, cycle = await _company(
        db_session, project_criteria={"auto_pause_if": PAUSE_IF}
    )
    await _measured(
        db_session, company, cycle, project=project,
        **{"newsroom.cost_per_published_article": "4.50"},
    )  # fmt: skip

    done = await _governance().review(db_session, cycle)

    (breach,) = done.breaches
    assert "4.5" in str(breach) and "> 3" in str(breach)
    assert any("kill criteria met" in w for w in done.warnings)
    assert done.paused_projects == []
    assert (await db_session.get(Project, project.id)).state == ProjectState.ACTIVE.value
    assert await _stopped(db_session, company) == []
    assert cycle.governance["breaches"] == [str(breach)]


async def test_a_project_inside_its_criteria_is_left_alone(db_session):
    company, unit, project, cycle = await _company(
        db_session, project_criteria={"auto_pause_if": PAUSE_IF}
    )
    await _measured(
        db_session, company, cycle, project=project,
        **{"newsroom.cost_per_published_article": "1.20"},
    )  # fmt: skip

    done = await _governance().review(db_session, cycle)

    assert not done.breaches
    assert (await db_session.get(Project, project.id)).state == ProjectState.ACTIVE.value


async def test_a_metric_nobody_measured_is_not_a_breach(db_session):
    """Silence is not evidence: a criterion on a number that was never computed does nothing."""
    company, unit, project, cycle = await _company(
        db_session, project_criteria={"auto_pause_if": PAUSE_IF}
    )
    await _measured(db_session, company, cycle, project=project, cost="9.99")

    done = await _governance().review(db_session, cycle)

    assert not done.paused_projects and not done.breaches


async def test_a_project_is_given_the_cycles_it_was_promised(db_session):
    """``evaluate_after_cycles``: judged only once it has had its run."""
    company, unit, project, cycle = await _company(
        db_session,
        seq=3,
        project_criteria={"evaluate_after_cycles": 7, "auto_pause_if": PAUSE_IF},
    )
    await _measured(
        db_session, company, cycle, project=project,
        **{"newsroom.cost_per_published_article": "99"},
    )  # fmt: skip

    done = await _governance().review(db_session, cycle)

    assert not done.breaches  # cycle 3 of the 7 it was given


async def test_a_criterion_that_needs_several_cycles_needs_all_of_them(db_session):
    company, unit, project, cycle = await _company(
        db_session,
        seq=2,
        project_criteria={
            "auto_pause_if": {**PAUSE_IF, "consecutive_cycles": 2},
        },
    )
    earlier = Cycle(
        company_id=company.id,
        seq=1,
        stage="DONE",
        started_at=START - timedelta(days=1),
        ended_at=END - timedelta(days=1),
    )
    db_session.add(earlier)
    await db_session.flush()
    # only the latest cycle is over the line
    await _measured(
        db_session, company, earlier, project=project,
        **{"newsroom.cost_per_published_article": "1.00"},
    )  # fmt: skip
    await _measured(
        db_session, company, cycle, project=project,
        **{"newsroom.cost_per_published_article": "5.00"},
    )  # fmt: skip

    assert not (await _governance().review(db_session, cycle)).breaches

    # now both are
    snapshot = await db_session.scalar(
        select(KpiSnapshot).where(KpiSnapshot.cycle_id == earlier.id)
    )
    snapshot.metrics = {"newsroom.cost_per_published_article": "6.00"}
    await db_session.flush()

    done = await _governance().review(db_session, cycle)

    assert done.breaches[0].cycles == 2
    assert done.paused_projects == []


async def test_an_unreadable_criterion_stops_nothing(db_session):
    """A typo in a rule must not pause a business; it is logged and skipped."""
    company, unit, project, cycle = await _company(
        db_session, project_criteria={"auto_pause_if": {"metric": "x", "op": "≫", "value": 1}}
    )
    await _measured(db_session, company, cycle, project=project, x="99")

    done = await _governance().review(db_session, cycle)

    assert not done.breaches


async def test_a_business_that_breaks_its_criteria_is_reported_and_keeps_working(db_session):
    """AI Media's cost per published article is exactly what a stuck desk breaks: stopping the
    business then would only stop it more (D-258)."""
    company, unit, project, cycle = await _company(
        db_session, unit_criteria={"auto_pause_if": PAUSE_IF}
    )
    await _measured(
        db_session, company, cycle, unit=unit,
        **{"newsroom.cost_per_published_article": "8"},
    )  # fmt: skip

    done = await _governance().review(db_session, cycle)

    assert len(done.breaches) == 1 and any("business" in w for w in done.warnings)
    assert done.paused_units == [] and done.paused_projects == []
    assert (await db_session.get(BusinessUnit, unit.id)).state == BusinessUnitState.ACTIVE.value
    assert (await db_session.get(Project, project.id)).state == ProjectState.ACTIVE.value
    assert await _stopped(db_session, company) == []


async def test_governance_stops_nothing_and_kills_nothing(db_session):
    """Only a person pauses or ends a project, from the back office (D-258)."""
    company, unit, project, cycle = await _company(
        db_session, project_criteria={"auto_pause_if": PAUSE_IF}
    )
    await _measured(
        db_session, company, cycle, project=project,
        **{"newsroom.cost_per_published_article": "99"},
    )  # fmt: skip

    await _governance().review(db_session, cycle)

    assert (await db_session.get(Project, project.id)).state == ProjectState.ACTIVE.value
    assert await _stopped(db_session, company) == []


async def test_running_the_rules_twice_reports_twice_and_changes_nothing(db_session):
    """MEASURING and REVIEWING can both be entered again after a restart."""
    company, unit, project, cycle = await _company(
        db_session, project_criteria={"auto_pause_if": PAUSE_IF}
    )
    await _measured(
        db_session, company, cycle, project=project,
        **{"newsroom.cost_per_published_article": "4"},
    )  # fmt: skip
    governance = _governance()

    first = await governance.review(db_session, cycle)
    again = await governance.review(db_session, cycle)

    assert len(first.breaches) == len(again.breaches) == 1
    assert await _stopped(db_session, company) == []


# --- 2. an agent that keeps failing -----------------------------------------------------------


async def _agent_with_runs(db_session, company, project, *states, errors=None):
    """``states`` oldest first. ``errors`` gives an error_class per run, for the failures whose
    cause matters (D-020: an outage is not the agent failing)."""
    position = await role_by_key(db_session, company.id, "ceo")
    agent = await hire_agent(
        db_session, company_id=company.id, role="ceo", display_name=f"A{uuid.uuid4().hex[:6]}",
        actor=HUMAN, position=position,
    )  # fmt: skip
    errors = errors or {}
    for n, state in enumerate(states):
        task = Task(
            company_id=company.id, project_id=project.id, name="plan", display_name="Plan",
            required_role="ceo", state="READY",
        )  # fmt: skip
        db_session.add(task)
        await db_session.flush()
        db_session.add(
            AgentRun(
                company_id=company.id,
                agent_id=agent.id,
                task_id=task.id,
                attempt=1,
                state=state,
                error=(
                    {"error_class": errors.get(n, "EvaluationFailed"), "message": "x"}
                    if state == "FAILED"
                    else None
                ),
                created_at=START + timedelta(minutes=n),
                started_at=START + timedelta(minutes=n),
                # the database enforces "finished_at iff terminal"
                finished_at=START + timedelta(minutes=n, seconds=30),
            )
        )
    await db_session.flush()
    return agent


async def test_an_agent_that_keeps_failing_is_reported_and_keeps_working(db_session):
    """In an office nobody is sent home by a rule: the findings are told, a person decides
    (D-258)."""
    company, unit, project, cycle = await _company(db_session)
    await bootstrap_executive(db_session, company.id, actor=HUMAN)
    agent = await _agent_with_runs(db_session, company, project, *(["FAILED"] * 3))

    done = await _governance().review(db_session, cycle)

    assert done.failing_agents == [agent.id] and done.paused_agents == []
    assert any(
        f"{FAILURES_BEFORE_PAUSE} different pieces of work in a row failed" in w
        for w in done.warnings
    )
    assert (await db_session.get(type(agent), agent.id)).status == AgentStatus.ACTIVE.value
    assert await _stopped(db_session, company) == []
    assert cycle.governance["failing_agents"] == [str(agent.id)]


async def test_a_failure_streak_broken_by_a_success_does_not_count(db_session):
    company, unit, project, cycle = await _company(db_session)
    await bootstrap_executive(db_session, company.id, actor=HUMAN)
    agent = await _agent_with_runs(db_session, company, project, "FAILED", "COMPLETED", "FAILED")

    done = await _governance().review(db_session, cycle)

    assert not done.failing_agents
    assert (await db_session.get(type(agent), agent.id)).status == AgentStatus.ACTIVE.value


async def test_a_new_agent_with_too_few_runs_is_not_judged(db_session):
    company, unit, project, cycle = await _company(db_session)
    await bootstrap_executive(db_session, company.id, actor=HUMAN)
    await _agent_with_runs(db_session, company, project, "FAILED", "FAILED")

    assert not (await _governance().review(db_session, cycle)).failing_agents


# --- 3. spending near a cap -------------------------------------------------------------------


async def test_a_budget_most_of_the_way_spent_is_announced(db_session):
    company, unit, project, cycle = await _company(db_session)
    db_session.add(
        Budget(company_id=company.id, project_id=project.id, period="cycle", amount=Decimal("10"))
    )
    await _measured(db_session, company, cycle, project=project, cost="8.50")

    done = await _governance().review(db_session, cycle)

    assert done.warnings and "85%" in done.warnings[0]
    event = await db_session.scalar(
        select(EventRecord).where(
            EventRecord.company_id == company.id, EventRecord.event_type == "BUDGET_WARNING"
        )
    )
    assert event.payload["ratio"] >= WARN_AT
    assert Decimal(str(event.payload["cap"])) == Decimal("10")


async def test_a_budget_barely_touched_says_nothing(db_session):
    company, unit, project, cycle = await _company(db_session)
    db_session.add(
        Budget(company_id=company.id, project_id=project.id, period="cycle", amount=Decimal("10"))
    )
    await _measured(db_session, company, cycle, project=project, cost="1.00")

    assert not (await _governance().review(db_session, cycle)).warnings


async def test_a_budget_already_at_the_wall_is_the_guard_s_business_not_this_one(db_session):
    """At 100% the cost guard refuses the call; repeating it here would be noise."""
    company, unit, project, cycle = await _company(db_session)
    db_session.add(
        Budget(company_id=company.id, project_id=project.id, period="cycle", amount=Decimal("10"))
    )
    await _measured(db_session, company, cycle, project=project, cost="10.00")

    assert not (await _governance().review(db_session, cycle)).warnings


# --- all of it together -----------------------------------------------------------------------


async def test_nothing_wrong_means_nothing_happens(db_session):
    company, unit, project, cycle = await _company(db_session)

    done = await _governance().review(db_session, cycle)

    assert not done
    assert (await db_session.get(Project, project.id)).state == ProjectState.ACTIVE.value


async def test_the_stage_hook_runs_the_rules(db_session):
    company, unit, project, cycle = await _company(
        db_session, project_criteria={"auto_pause_if": PAUSE_IF}
    )
    await _measured(
        db_session, company, cycle, project=project,
        **{"newsroom.cost_per_published_article": "7"},
    )  # fmt: skip

    await _governance().stage_hook()(db_session, cycle)

    assert len(cycle.governance["breaches"]) == 1
    assert (await db_session.get(Project, project.id)).state == ProjectState.ACTIVE.value


async def test_the_rules_never_call_a_model(db_session):
    """Deterministic by construction: they hold when the CEO is slow, wrong or absent."""
    company, unit, project, cycle = await _company(
        db_session, project_criteria={"auto_pause_if": PAUSE_IF}
    )
    await _measured(
        db_session, company, cycle, project=project,
        **{"newsroom.cost_per_published_article": "7"},
    )  # fmt: skip

    await _governance().review(db_session, cycle)

    calls = await db_session.scalar(select(ModelCall.id).where(ModelCall.company_id == company.id))
    assert calls is None


async def test_reporting_and_governance_agree_on_the_numbers(db_session):
    """Governance reads what Reporting wrote: one measurement, one decision."""
    company, unit, project, cycle = await _company(
        db_session,
        project_criteria={"auto_pause_if": {"metric": "cost", "op": ">", "value": 1}},
    )
    db_session.add(
        ModelCall(
            company_id=company.id,
            project_id=project.id,
            role="writer",
            capability="drafting",
            alias="frontier",
            provider="nvidia",
            model_id="m",
            status="ok",
            cost_usd=Decimal("2.50"),
            created_at=START + timedelta(hours=1),
        )  # fmt: skip
    )
    await db_session.flush()
    await Reporting(clock=lambda: END).measure_cycle(db_session, cycle)

    done = await _governance().review(db_session, cycle)

    assert [b.scope_id for b in done.breaches] == [project.id]
    assert done.breaches[0].observed == 80  # the meter's $2.50, reported in TWD at 32


# --- the system's old pauses are lifted, a person's stay (D-258) --------------------------------


async def test_a_pause_the_system_made_is_lifted_and_a_person_s_stays(db_session):
    from autora.company.agents.roster import pause_agent
    from autora.company.governance import LIFTED_REASON, lift_system_pauses

    company, unit, project, cycle = await _company(db_session)
    await bootstrap_executive(db_session, company.id, actor=HUMAN)
    by_rule = await _agent_with_runs(db_session, company, project, "COMPLETED")
    by_hand = await _agent_with_runs(db_session, company, project, "COMPLETED")
    await pause_agent(
        db_session, by_rule, actor=Actor.system("governance"), reason="3 runs in a row failed"
    )
    await pause_agent(db_session, by_hand, actor=HUMAN, reason="taking a break")

    lifted = await lift_system_pauses(db_session)

    assert by_rule.id in lifted and by_hand.id not in lifted
    assert (await db_session.get(type(by_rule), by_rule.id)).status == AgentStatus.ACTIVE.value
    assert (await db_session.get(type(by_hand), by_hand.id)).status == AgentStatus.PAUSED.value
    resumed = await db_session.scalar(
        select(EventRecord).where(
            EventRecord.agent_id == by_rule.id, EventRecord.event_type == "AGENT_RESUMED"
        )
    )
    assert resumed.payload["reason"] == LIFTED_REASON
    assert by_rule.id not in await lift_system_pauses(db_session), "lifted once"


# --- what one failure is: a piece of work, not a run (D-257) -------------------------------------


async def _agent_with_work(db_session, company, project, *pieces):
    """``pieces`` oldest first, each the states of its runs in order: one workflow run per piece
    (a story), each run on its own task in it — as a story's rounds and tries are."""
    position = await role_by_key(db_session, company.id, "ceo")
    agent = await hire_agent(
        db_session, company_id=company.id, role="ceo", display_name=f"W{uuid.uuid4().hex[:6]}",
        actor=HUMAN, position=position,
    )  # fmt: skip
    minute = 0
    for states in pieces:
        run = WorkflowRun(
            company_id=company.id,
            project_id=project.id,
            template_name="newsroom.story_to_article_v2",
        )
        db_session.add(run)
        await db_session.flush()
        for state in states:
            task = Task(
                company_id=company.id, project_id=project.id, workflow_run_id=run.id, name="draft",
                display_name="Draft", required_role="ceo", state="READY",
            )  # fmt: skip
            db_session.add(task)
            await db_session.flush()
            db_session.add(
                AgentRun(
                    company_id=company.id, agent_id=agent.id, task_id=task.id, attempt=1,
                    state=state,
                    error={"error_class": "MaxStepsExceeded", "message": "x"}
                    if state == "FAILED" else None,
                    created_at=START + timedelta(minutes=minute),
                    started_at=START + timedelta(minutes=minute),
                    finished_at=START + timedelta(minutes=minute, seconds=30),
                )
            )  # fmt: skip
            minute += 1
    await db_session.flush()
    return agent


async def test_one_story_the_agent_cannot_get_past_does_not_pause_it(db_session):
    """2026-10-18: two rounds of one story's draft, three tries each, all failed — after two
    stories written. Counted by runs it paused the writer for three days."""
    company, unit, project, cycle = await _company(db_session)
    await bootstrap_executive(db_session, company.id, actor=HUMAN)
    agent = await _agent_with_work(
        db_session, company, project, ["COMPLETED"], ["COMPLETED"], ["FAILED"] * 6
    )

    assert (await _governance().review(db_session, cycle)).failing_agents == []
    assert (await db_session.get(type(agent), agent.id)).status == AgentStatus.ACTIVE.value


async def test_three_tries_at_one_task_are_one_failure(db_session):
    company, unit, project, cycle = await _company(db_session)
    await bootstrap_executive(db_session, company.id, actor=HUMAN)
    agent = await _agent_with_runs(db_session, company, project, "COMPLETED", "COMPLETED")
    task = Task(
        company_id=company.id, project_id=project.id, name="plan", display_name="Plan",
        required_role="ceo", state="READY",
    )  # fmt: skip
    db_session.add(task)
    await db_session.flush()
    for n in range(3):
        db_session.add(
            AgentRun(
                company_id=company.id, agent_id=agent.id, task_id=task.id, attempt=n + 1,
                state="FAILED", error={"error_class": "EvaluationFailed", "message": "x"},
                created_at=START + timedelta(hours=1, minutes=n),
                started_at=START + timedelta(hours=1, minutes=n),
                finished_at=START + timedelta(hours=1, minutes=n, seconds=30),
            )
        )  # fmt: skip
    await db_session.flush()

    assert (await _governance().review(db_session, cycle)).failing_agents == []


async def test_three_stories_failed_in_a_row_are_reported(db_session):
    """An agent that cannot do its job is still found: three different stories, each failed."""
    company, unit, project, cycle = await _company(db_session)
    await bootstrap_executive(db_session, company.id, actor=HUMAN)
    agent = await _agent_with_work(
        db_session, company, project, ["COMPLETED"], ["FAILED"], ["FAILED", "FAILED"], ["FAILED"]
    )

    assert (await _governance().review(db_session, cycle)).failing_agents == [agent.id]


async def test_a_story_whose_last_try_succeeded_is_not_a_failure(db_session):
    company, unit, project, cycle = await _company(db_session)
    await bootstrap_executive(db_session, company.id, actor=HUMAN)
    await _agent_with_work(
        db_session, company, project, ["FAILED"], ["FAILED"], ["FAILED", "FAILED", "COMPLETED"]
    )

    assert (await _governance().review(db_session, cycle)).failing_agents == []


# --- whose failure was it? (D-020, found by the first real-model soak) ------------------------


async def test_an_outage_is_not_the_agent_failing(db_session):
    """A bad afternoon at the provider must not suspend the company's executive.

    This is what the 2026-09-21 real-model soak did: three 504s in a row and the CEO was paused
    for the rest of the week, so every remaining day fell back.
    """
    company, unit, project, cycle = await _company(db_session)
    await bootstrap_executive(db_session, company.id, actor=HUMAN)
    agent = await _agent_with_runs(
        db_session,
        company,
        project,
        *(["FAILED"] * 3),
        errors=dict.fromkeys(range(3), "ProviderError"),
    )

    done = await _governance().review(db_session, cycle)

    assert done.failing_agents == []
    assert (await db_session.get(type(agent), agent.id)).status == AgentStatus.ACTIVE.value


async def test_the_other_things_that_are_not_the_agent_s_fault(db_session):
    company, unit, project, cycle = await _company(db_session)
    await bootstrap_executive(db_session, company.id, actor=HUMAN)
    agent = await _agent_with_runs(
        db_session,
        company,
        project,
        *(["FAILED"] * 3),
        errors={0: "LeaseExpired", 1: "BudgetExhausted", 2: "Aborted:timeout"},
    )

    assert (await _governance().review(db_session, cycle)).failing_agents == []
    assert (await db_session.get(type(agent), agent.id)).status == AgentStatus.ACTIVE.value


async def test_outages_do_not_hide_the_agent_s_own_failures(db_session):
    """Skipped, not counted as successes: three of its own in a row are still reported."""
    company, unit, project, cycle = await _company(db_session)
    await bootstrap_executive(db_session, company.id, actor=HUMAN)
    agent = await _agent_with_runs(
        db_session,
        company,
        project,
        "FAILED",
        "FAILED",
        "FAILED",
        "FAILED",
        errors={1: "ProviderError"},  # an outage in the middle of its own three
    )

    done = await _governance().review(db_session, cycle)

    assert done.failing_agents == [agent.id]
    assert (await db_session.get(type(agent), agent.id)).status == AgentStatus.ACTIVE.value


async def test_a_success_under_the_outages_still_breaks_the_streak(db_session):
    company, unit, project, cycle = await _company(db_session)
    await bootstrap_executive(db_session, company.id, actor=HUMAN)
    await _agent_with_runs(
        db_session,
        company,
        project,
        "FAILED",
        "COMPLETED",
        "FAILED",
        "FAILED",
        errors={2: "ProviderError"},
    )

    assert (await _governance().review(db_session, cycle)).failing_agents == []
