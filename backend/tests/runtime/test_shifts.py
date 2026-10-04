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


MARKETS = (
    "mon-fri 08:00-09:00,13:30-14:30; "  # Taiwan: an hour before the open, after the close
    "mon-fri 08:30-09:30,16:00-17:00 America/New_York; "  # New York's, the same, in its own time
    "sat-sun 09:00-10:00"
)


def test_an_hour_before_each_market_opens_and_an_hour_after_it_closes():
    """D-195: Taiwan's in Taipei time, New York's in New York time, weekends an hour."""
    s = Shifts.parse(MARKETS, timezone="Asia/Taipei")
    assert s is not None
    assert s.on_duty(taipei(5, 8, 30)) and s.on_duty(taipei(5, 14)) and not s.on_duty(taipei(5, 12))
    # New York in daylight saving (until 2026-11-01): 08:30 there is 20:30 in Taipei, 16:00 is 04:00
    assert s.on_duty(taipei(5, 20, 45)) and s.on_duty(taipei(6, 4, 30))
    assert not s.on_duty(taipei(5, 22)) and not s.on_duty(taipei(6, 5, 30))
    # and in winter time an hour later in Taipei, with no change to the setting
    november = datetime(2026, 11, 2, 21, 45, tzinfo=ZoneInfo("Asia/Taipei"))  # a Monday
    assert s.on_duty(november) and not s.on_duty(november.replace(hour=20))
    # Monday morning Taipei is still Sunday in New York: no US shift then
    assert not s.on_duty(taipei(5, 4, 30))
    assert s.on_duty(taipei(10, 9, 30)) and not s.on_duty(taipei(10, 8))  # Saturday
    assert s.next_start(taipei(5, 9, 10)) == taipei(5, 13, 30)
    assert s.next_start(taipei(5, 14, 40)) == taipei(5, 20, 30)
    assert s.next_start(taipei(5, 21, 40)) == taipei(6, 4)
    assert s.hours_a_week() == 5 * 4 + 2 * 1


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
