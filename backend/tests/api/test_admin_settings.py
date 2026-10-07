"""AD-11: what the back office tunes while everything runs — checked before it is kept, kept with
what it was before and after, in force at once in the API (office hours answer from memory) and
in the worker at its next pass or call, back to the environment's on reset; an owner's only."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from autora.db.models import SystemSetting, SystemSettingChange
from autora.infra.settings import load_settings
from autora.runtime.live_settings import (
    DEFINITIONS,
    LiveOvertime,
    LiveShifts,
    SettingError,
    normalize,
    worker_reloader,
)
from autora.runtime.shifts import Shifts
from autora_api.live import LIVE
from tests.conftest import unique_company

SETTINGS = "/api/admin/settings"


@pytest.fixture(autouse=True)
def _forget_live_values():
    LIVE.overrides = {}
    yield
    LIVE.overrides = {}


def _env():
    return load_settings(worker_shifts="", worker_overtime_day_hours=4, contact_daily_cap=30)


def test_a_value_is_checked_before_it_is_kept():
    env = _env()
    assert normalize(env, "worker.shifts", "  mon-fri 15:00-21:00; sat-sun 18:00-21:00 ") == (
        "mon-fri 15:00-21:00; sat-sun 18:00-21:00"
    )
    assert normalize(env, "worker.shifts", "") == ""  # all day
    for wrong in ("tuesday at noon", 15):
        with pytest.raises(SettingError):
            normalize(env, "worker.shifts", wrong)
    assert normalize(env, "worker.overtime_day_hours", 2.5) == 2.5
    for wrong in (5, -1, "3", True):
        with pytest.raises(SettingError):
            normalize(env, "worker.overtime_day_hours", wrong)
    assert normalize(env, "contact.daily_cap", 50) == 50
    with pytest.raises(SettingError):
        normalize(env, "contact.daily_cap", 2.5)
    with pytest.raises(SettingError):
        normalize(env, "nothing.like.it", 1)


async def test_set_it_reset_it_and_keep_what_it_was(api, db_session):
    listed = (await api.get(SETTINGS)).json()
    assert [s["key"] for s in listed] == list(DEFINITIONS)
    shifts = next(s for s in listed if s["key"] == "worker.shifts")
    assert (shifts["overridden"], shifts["value"], shifts["changes"]) == (
        False,
        shifts["default"],
        [],
    )

    first = await api.put(f"{SETTINGS}/worker.shifts", json={"value": "mon-fri 09:00-12:00"})
    assert first.status_code == 200, first.text
    await api.put(f"{SETTINGS}/worker.shifts", json={"value": "mon-sun 08:00-23:00"})
    shifts = next(s for s in (await api.get(SETTINGS)).json() if s["key"] == "worker.shifts")
    assert (shifts["overridden"], shifts["value"]) == (True, "mon-sun 08:00-23:00")
    assert shifts["updated_by"]["id"] == "operator"
    assert shifts["changes"][0]["actor_label"] == "操作者權杖"
    assert [(c["before"], c["after"]) for c in shifts["changes"]] == [
        ("mon-fri 09:00-12:00", "mon-sun 08:00-23:00"),
        (None, "mon-fri 09:00-12:00"),
    ]

    # in force at once, without a deploy: office hours answer from memory
    hours = (await api.get("/api/office-hours")).json()
    assert hours["shifts"] == ["mon-sun 08:00-23:00"]

    reset = await api.delete(f"{SETTINGS}/worker.shifts")
    shifts = next(s for s in reset.json() if s["key"] == "worker.shifts")
    assert (shifts["overridden"], shifts["value"]) == (False, shifts["default"])
    assert (shifts["changes"][0]["before"], shifts["changes"][0]["after"]) == (
        "mon-sun 08:00-23:00",
        None,
    )
    assert "worker.shifts" not in LIVE.overrides
    assert await db_session.get(SystemSetting, "worker.shifts") is None


async def test_what_cannot_be_kept_is_refused(api):
    bad = await api.put(f"{SETTINGS}/worker.overtime_month_hours", json={"value": 47})
    assert bad.status_code == 422 and "at most 46" in bad.json()["detail"]
    assert (
        await api.put(f"{SETTINGS}/worker.shifts", json={"value": "whenever"})
    ).status_code == 422
    assert (await api.put(f"{SETTINGS}/no.such", json={"value": 1})).status_code == 404
    assert (await api.get(SETTINGS, headers={"Authorization": ""})).status_code == 401


async def test_the_record_of_changes_cannot_be_edited(api, db_session):
    await api.put(f"{SETTINGS}/contact.daily_cap", json={"value": 50})
    change = await db_session.scalar(
        select(SystemSettingChange).where(SystemSettingChange.key == "contact.daily_cap")
    )
    with pytest.raises(DBAPIError, match="append-only"):
        async with db_session.begin_nested():
            await db_session.execute(
                text("DELETE FROM system_setting_changes WHERE id = :id"), {"id": change.id}
            )


async def test_the_api_reads_them_back_at_its_start(committed):
    key = "contact.daily_cap"
    async with committed() as session:
        await session.merge(
            SystemSetting(key=key, value=7, updated_by={"kind": "human", "id": "t"})
        )
        await session.commit()
    try:
        await LIVE.recall(committed)
        assert LIVE.value(_env(), key) == 7
    finally:
        async with committed() as session:
            await session.execute(text("DELETE FROM system_settings WHERE key = :k"), {"k": key})
            await session.commit()


async def test_the_worker_takes_them_at_a_pass_and_before_a_call(db_session, committed):
    env = _env()
    company = await unique_company(db_session, "live")
    assert company
    shifts = LiveShifts(Shifts.parse("mon-fri 15:00-21:00", "mon-sun", "Asia/Taipei"))
    overtime = LiveOvertime(committed, day_limit=timedelta(hours=1), month_limit=timedelta(hours=1))
    reload, in_pass = worker_reloader(env, committed, shifts, overtime)
    overtime.reload = reload

    # nothing set: the environment's
    await in_pass(db_session)
    assert shifts.shifts is None and shifts.on_duty(datetime.now(UTC))  # env "": all day
    assert overtime.day_limit == timedelta(hours=4)

    async with committed() as session:
        for key, value in (
            ("worker.shifts", "mon-sun 03:00-04:00"),
            ("worker.overtime_day_hours", 2),
        ):
            await session.merge(
                SystemSetting(key=key, value=value, updated_by={"kind": "human", "id": "t"})
            )
        await session.commit()
    try:
        # a call about to begin reads them first
        await overtime.left(datetime.now(UTC))
        assert overtime.day_limit == timedelta(hours=2)
        assert shifts.shifts is not None
        three = datetime(2026, 10, 8, 3, 30, tzinfo=shifts.shifts.rosters[0].zone)
        assert shifts.on_duty(three) and not shifts.on_duty(three + timedelta(hours=1))
    finally:
        async with committed() as session:
            await session.execute(text("DELETE FROM system_settings WHERE key LIKE 'worker.%'"))
            await session.commit()
