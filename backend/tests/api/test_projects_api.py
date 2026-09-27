"""D-056: pausing and resuming a project from the admin dashboard."""

from datetime import UTC, datetime

from sqlalchemy import select

from autora.company.events import ProjectPaused
from autora.db.models import CommandRecord, Cycle, Project, ProjectState
from autora.runtime.actor import Actor
from autora.runtime.events.outbox import emit
from autora.runtime.events.schema import new_event
from tests.conftest import unique_company

URL = "/api/companies/{}/projects"


async def _project(db_session, state=ProjectState.ACTIVE):
    company = await unique_company(db_session, "prj")
    project = Project(
        company_id=company.id, name="持股動態", state=state.value, kill_criteria={"max_cost_usd": 5}
    )
    db_session.add(project)
    await db_session.flush()
    return company, project


async def test_an_operator_pauses_and_resumes_through_the_command_bus(api, db_session):
    company, project = await _project(db_session)
    base = URL.format(company.id) + f"/{project.id}"

    paused = await api.post(base + "/pause", json={"reason": "先停一下"})
    assert paused.status_code == 200, paused.text
    assert paused.json()["decision"] == "allow" and paused.json()["state"] == "PAUSED"
    [line] = (await api.get(URL.format(company.id))).json()
    assert line["state"] == "PAUSED" and line["paused_by"] == "human"
    assert line["pause_reason"] == "先停一下"

    resumed = await api.post(base + "/resume", json={})
    assert resumed.json()["state"] == "ACTIVE"
    verbs = (
        await db_session.scalars(
            select(CommandRecord.command).where(CommandRecord.company_id == company.id)
        )
    ).all()
    assert sorted(verbs) == ["PauseProject", "ResumeProject"]


async def test_resuming_an_active_project_is_refused_not_an_error(api, db_session):
    company, project = await _project(db_session)
    answer = await api.post(URL.format(company.id) + f"/{project.id}/resume", json={})
    assert answer.status_code == 200
    assert answer.json()["state"] == "ACTIVE" and answer.json()["outcome"] != "done"
    assert "not PAUSED" in answer.json()["reason"]


async def test_a_ceo_pause_shows_the_ceo_s_rationale(api, db_session):
    """Cycle 5: the CEO paused the newsroom with no reason on the event, only in its review."""
    company, project = await _project(db_session, ProjectState.PAUSED)
    db_session.add(
        Cycle(company_id=company.id, seq=1, stage="DONE", ended_at=datetime.now(UTC), review={
            "projects": [{"project_id": str(project.id), "decision": "pause",
                          "rationale": "No revenue; pause to reduce burn."}],
        })
    )  # fmt: skip
    await emit(
        db_session,
        new_event(
            ProjectPaused(name=project.name, reason=None, trigger="ceo"),
            company_id=company.id,
            actor=Actor.human("ceo-test"),
            aggregate_type="project",
            aggregate_id=project.id,
        ),
    )
    await db_session.flush()
    [line] = (await api.get(URL.format(company.id))).json()
    assert (
        line["paused_by"] == "ceo" and line["pause_reason"] == "No revenue; pause to reduce burn."
    )


async def test_another_company_s_project_is_not_found(api, db_session):
    company, _ = await _project(db_session)
    _, other = await _project(db_session)
    answer = await api.post(URL.format(company.id) + f"/{other.id}/pause", json={})
    assert answer.status_code == 404


async def test_it_is_an_operator_s(api, db_session):
    company, _ = await _project(db_session)
    assert (await api.get(URL.format(company.id), headers={"Authorization": ""})).status_code == 401
