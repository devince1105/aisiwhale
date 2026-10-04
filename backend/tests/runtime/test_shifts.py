"""D-193: office hours — the worker works its shifts and leaves the database alone between them."""

import asyncio
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

from autora.runtime.shifts import Shifts, ShiftsError
from autora.runtime.worker import Worker

TAIPEI_SHIFTS = Shifts.parse("07:00-11:00,19:00-23:00", "mon-fri", "Asia/Taipei")


def taipei(day: int, hour: int, minute: int = 0) -> datetime:
    """A moment in Taipei, 2026-10-``day`` (the 5th is a Monday)."""
    return datetime(2026, 10, day, hour, minute, tzinfo=ZoneInfo("Asia/Taipei"))


def test_two_shifts_on_weekdays():
    s = TAIPEI_SHIFTS
    assert s is not None
    assert s.on_duty(taipei(5, 7)) and s.on_duty(taipei(5, 10, 59))
    assert not s.on_duty(taipei(5, 11)) and not s.on_duty(taipei(5, 15))
    assert s.on_duty(taipei(5, 19, 30)) and not s.on_duty(taipei(5, 23))
    assert not s.on_duty(taipei(10, 9))  # Saturday


def test_the_next_clock_in():
    s = TAIPEI_SHIFTS
    assert s is not None
    assert s.next_start(taipei(5, 12)) == taipei(5, 19)  # the evening shift, the same day
    assert s.next_start(taipei(5, 23, 30)) == taipei(6, 7)  # tomorrow morning
    assert s.next_start(taipei(9, 23, 30)) == taipei(12, 7)  # Friday night: Monday morning
    assert s.next_start(taipei(10, 12)) == taipei(12, 7)  # Saturday


def test_no_shifts_is_always_at_work_and_nonsense_is_refused():
    assert Shifts.parse("") is None
    for spec, days in (("7-11", "mon-fri"), ("11:00-07:00", "mon-fri"), ("07:00-11:00", "funday")):
        with pytest.raises(ShiftsError):
            Shifts.parse(spec, days)


async def test_off_duty_the_worker_does_nothing_until_its_shift():
    ticks: list[int] = []
    off = Shifts.parse("07:00-08:00", "mon-sun", "UTC")

    class Clocked:
        poll_interval = 0.01
        idle_poll_interval = 0.01
        worker_id = "clocked"
        concurrency = 1
        shifts = off
        _running: dict = {}

        def clock(self):
            return datetime(2026, 10, 5, 12, 0, tzinfo=UTC)  # long after the shift

        async def tick(self):
            ticks.append(1)
            return 0

        async def shutdown(self):
            pass

        _off_duty = Worker._off_duty

    stop = asyncio.Event()
    asyncio.get_running_loop().call_later(0.3, stop.set)
    await Worker.run_forever(Clocked(), stop)  # type: ignore[arg-type]
    assert ticks == []  # not one pass, not one query
