"""D-193: the admin can see when the AI staff work; D-205: and that the worker was called."""

import uuid

from autora.infra.settings import load_settings
from autora_api.deps import settings_dep
from tests.api.conftest import TOKEN


async def test_always_at_work_without_shifts(api):
    got = (await api.get("/api/office-hours")).json()
    assert got["shifts"] == [] and got["on_duty"] is True and got["next_start"] is None


async def test_shifts_and_the_next_clock_in(api, db_settings):
    api._transport.app.dependency_overrides[settings_dep] = lambda: load_settings(
        database_url=db_settings.database_url,
        api_bearer_token=TOKEN,
        worker_shifts="00:00-00:01",
        worker_days="mon-sun",
        worker_timezone="UTC",
    )
    got = (await api.get("/api/office-hours", headers={"Authorization": f"Bearer {TOKEN}"})).json()
    assert got["shifts"] == ["00:00-00:01"] and got["timezone"] == "UTC"
    if not got["on_duty"]:
        assert got["next_start"].endswith(("T00:00:00Z", "T00:00:00+00:00"))


async def test_changing_something_calls_the_worker_and_reading_does_not(api):
    """D-205: off its shifts the worker comes in when a person has changed something."""
    from autora_api.deps import OFFICE_CALL

    OFFICE_CALL.at = None
    await api.get("/api/office-hours")
    assert OFFICE_CALL.at is None  # reading calls nobody

    # an approval decided — this one is not there, but the person did act
    await api.post(f"/api/approvals/{uuid.uuid4()}/decide", json={"decision": "approve"})
    assert OFFICE_CALL.at is not None
    got = (await api.get("/api/office-hours")).json()
    assert got["called_at"] is not None  # the office page can say the worker was called


async def test_only_the_worker_s_token_is_answered(api, db_settings):
    from autora_api.deps import OFFICE_CALL

    OFFICE_CALL.mark()
    # no WORKER_CALL_TOKEN set: not answered at all, not even to the operator
    assert (await api.get("/api/office-hours/call")).status_code == 401

    api._transport.app.dependency_overrides[settings_dep] = lambda: load_settings(
        database_url=db_settings.database_url,
        api_bearer_token=TOKEN,
        worker_call_token="worker-secret",
    )
    assert (await api.get("/api/office-hours/call")).status_code == 401  # the operator's: no
    got = await api.get("/api/office-hours/call", headers={"Authorization": "Bearer worker-secret"})
    assert got.status_code == 200
    assert got.json()["called_at"].startswith(OFFICE_CALL.at.strftime("%Y-%m-%dT%H:%M"))


async def test_the_worker_s_question_and_the_api_s_answer_agree(api, db_settings):
    """The worker's own client against the API itself: the URL, the token, the time's format."""
    import httpx

    from autora.runtime.oncall import api_caller
    from autora_api.deps import OFFICE_CALL

    app = api._transport.app
    app.dependency_overrides[settings_dep] = lambda: load_settings(
        database_url=db_settings.database_url,
        api_bearer_token=TOKEN,
        worker_call_token="worker-secret",
    )
    url = "http://api.test/api/office-hours/call"
    transport = httpx.ASGITransport(app=app)

    OFFICE_CALL.at = None
    ask = api_caller(url, "worker-secret", transport=transport)
    assert await ask() is None  # nobody has called yet

    await api.post(f"/api/approvals/{uuid.uuid4()}/decide", json={"decision": "approve"})
    assert await ask() == OFFICE_CALL.at

    assert await api_caller(url, "wrong", transport=transport)() is None  # refused: no call


async def test_a_restarted_api_remembers_the_call(api, db_session):
    """D-237: the call is written down when a person acts, and an API that starts afresh reads it
    back — a deploy in the minute after a person acts, or in the middle of a call, no longer
    loses it. Reading writes nothing."""
    from datetime import timedelta

    from sqlalchemy import func, select
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from autora.db.models import OfficeCallRecord
    from autora_api.deps import OFFICE_CALL, OfficeCall

    count = select(func.count()).select_from(OfficeCallRecord)
    OFFICE_CALL.at = None
    await api.get("/api/office-hours")
    assert await db_session.scalar(count) == 0  # reading calls nobody, and writes nothing

    await api.post(f"/api/approvals/{uuid.uuid4()}/decide", json={"decision": "approve"})
    called = OFFICE_CALL.at
    factory = async_sessionmaker(
        bind=await db_session.connection(), join_transaction_mode="create_savepoint"
    )
    restarted = OfficeCall()  # a new process: nothing in memory
    await restarted.recall(factory)
    assert restarted.at == called

    OFFICE_CALL.at = called - timedelta(hours=1)  # a clock behind: the record does not go back
    await OFFICE_CALL.keep(await db_session.connection())
    assert await db_session.scalar(select(OfficeCallRecord.called_at)) == called
    assert await db_session.scalar(count) == 1
