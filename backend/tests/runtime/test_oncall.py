"""D-205: on call — off its shifts the worker comes in when a person has just acted, within the
overtime 勞基法 would allow, and goes home when the work is done."""

import asyncio
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import async_sessionmaker

from autora.runtime.oncall import Call, Overtime
from autora.runtime.shifts import Shifts
from autora.runtime.worker import Worker

NOON = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)
OFF = Shifts.parse("07:00-08:00", "mon-sun", "UTC")  # noon is long after it


class Ledger:
    """Overtime without a database: what is left, and the calls written down."""

    def __init__(self, left: timedelta = timedelta(hours=4)):
        self._left = left
        self.calls: list[tuple[datetime, datetime]] = []

    async def left(self, now):
        return self._left

    async def record(self, start, end):
        self.calls.append((start, end))


class Scripted(Worker):
    """A worker whose passes are scripted: busy for ``work`` passes after it comes in, then idle."""

    def __init__(self, *, called_at, work=3, overtime=None, covered_until=None):
        loop = asyncio.get_running_loop()
        started = loop.time()

        async def ask():
            self.asked += 1
            return called_at

        super().__init__(
            worker_id="on-call",
            session_factory=None,  # type: ignore[arg-type]  # never reached: tick is scripted
            task_manager=None,  # type: ignore[arg-type]
            runner=None,  # type: ignore[arg-type]
            approvals=None,  # type: ignore[arg-type]
            poll_interval=0.005,
            idle_poll_interval=0.005,
            shifts=OFF,
            on_call=ask,
            overtime=overtime,
            call_poll_interval=0.01,
            call_idle=0.05,
            call_limit=3600,
            clock=lambda: NOON + timedelta(seconds=loop.time() - started),
        )
        self._covered_until = covered_until
        self.work = work
        self.ticks = 0
        self.asked = 0

    async def tick(self):
        self.ticks += 1
        return 1 if self.ticks <= self.work else 0

    async def shutdown(self):
        pass


async def _run(worker: Worker, seconds: float = 0.4) -> None:
    stop = asyncio.Event()
    asyncio.get_running_loop().call_later(seconds, stop.set)
    await worker.run_forever(stop)


async def test_a_person_acts_and_the_worker_comes_in_until_the_work_is_done():
    ledger = Ledger()
    worker = Scripted(called_at=NOON + timedelta(milliseconds=1), overtime=ledger)
    await _run(worker)

    assert worker.ticks > worker.work  # it worked, and passed idle for a while
    assert worker.ticks < 60  # and went home: not a pass every 5 ms for 0.4 s
    assert worker._call is None
    ((start, end),) = ledger.calls  # one call, written down as overtime
    assert timedelta(seconds=0.05) <= end - start < timedelta(seconds=0.3)
    assert worker.asked > 1  # back off duty, it kept asking — and the same call is not taken twice


async def test_no_call_no_work():
    worker = Scripted(called_at=None, overtime=Ledger())
    await _run(worker, 0.1)
    assert worker.ticks == 0 and worker.asked > 0


async def test_overtime_used_up_means_the_next_shift():
    """勞基法: no overtime left today or this month, no coming in — the work waits for the shift."""
    ledger = Ledger(left=timedelta(0))
    worker = Scripted(called_at=NOON + timedelta(milliseconds=1), overtime=ledger)
    await _run(worker, 0.1)
    assert worker.ticks == 0 and ledger.calls == []


async def test_what_it_was_at_work_for_already_is_not_a_call():
    """A person acted while the worker was still on its shift: it saw that; no overtime for it."""
    worker = Scripted(
        called_at=NOON - timedelta(minutes=5),
        covered_until=NOON - timedelta(minutes=1),
        overtime=Ledger(),
    )
    await _run(worker, 0.1)
    assert worker.ticks == 0


async def test_a_worker_just_started_does_not_answer_a_call_from_long_ago():
    worker = Scripted(called_at=NOON - timedelta(hours=2), overtime=Ledger())
    await _run(worker, 0.1)
    assert worker.ticks == 0


async def test_a_call_lasts_no_longer_than_the_overtime_left():
    """The limit is what is left, when that is less than an hour: then home, busy or not."""
    ledger = Ledger(left=timedelta(seconds=0.08))
    worker = Scripted(called_at=NOON + timedelta(milliseconds=1), work=10_000, overtime=ledger)
    await _run(worker, 0.3)
    ((start, end),) = ledger.calls
    assert timedelta(seconds=0.08) <= end - start < timedelta(seconds=0.2)


async def test_a_call_cut_short_by_a_deploy_still_counts_its_overtime():
    """D-237: a deploy stops the worker in the middle of a call; the time it was in is still
    overtime, written down as it goes."""
    ledger = Ledger()
    worker = Scripted(called_at=NOON + timedelta(milliseconds=1), work=10_000, overtime=ledger)
    await _run(worker, 0.2)
    ((start, end),) = ledger.calls
    assert timedelta(seconds=0.1) <= end - start < timedelta(seconds=0.3)


class Hours:
    """A scheduler whose due schedule takes hours: ``newsroom.refresh_prices`` once 93 more US
    stocks were tracked on 10/06 — 120 of them asked of Tiingo 75 seconds apart."""

    def __init__(self):
        self.passes = 0

    async def tick(self):
        self.passes += 1
        await asyncio.sleep(3600)
        return []


class Nothing:
    """Nothing to reap or expire, and a session that only commits."""

    async def reap_expired_leases(self, session):
        return []

    async def expire_due(self, session):
        return []

    def __call__(self):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return None

    async def commit(self):
        pass


class Desk(Worker):
    """A worker with a real pass — maintenance, schedules, dispatch — whose dispatch only notes
    when it was reached, and whether the worker was on a call then."""

    def __init__(self, *, start, called_at=None, shifts=OFF, overtime=None):
        loop = asyncio.get_running_loop()
        began = loop.time()
        self.dispatched: list[bool] = []

        async def ask():
            return called_at

        super().__init__(
            worker_id="desk",
            session_factory=Nothing(),  # type: ignore[arg-type]
            task_manager=Nothing(),  # type: ignore[arg-type]
            runner=None,  # type: ignore[arg-type]
            approvals=Nothing(),  # type: ignore[arg-type]
            scheduler=Hours(),  # type: ignore[arg-type]
            poll_interval=0.005,
            idle_poll_interval=0.005,
            maintenance_interval=0.01,
            grace=0.05,
            shifts=shifts,
            on_call=ask,
            overtime=overtime,
            call_poll_interval=0.01,
            call_idle=0.05,
            call_limit=3600,
            clock=lambda: start + timedelta(seconds=loop.time() - began),
        )

    async def dispatch(self):
        self.dispatched.append(self._call is not None)
        return 0


async def test_a_schedule_that_takes_hours_does_not_hold_up_the_shift():
    """D-237: on 10/06 the 18:20 price refresh held the worker's pass from 18:20 until a deploy
    at 20:34 — no task claimed, no other schedule fired. The schedules run beside the passes now,
    one scheduler pass at a time."""
    worker = Desk(start=NOON, shifts=None)
    await asyncio.wait_for(_run(worker, 0.3), timeout=2)  # and a stop is not held up either
    assert len(worker.dispatched) > 10  # pass after pass while the schedule runs
    assert worker.scheduler.passes == 1  # not a second one beside the first


async def test_the_night_of_10_06_a_call_while_the_shift_s_schedule_still_runs():
    """D-237: the shift ends during a schedule that takes hours, and a person sends a draft back
    afterwards. The worker comes in for it at once — and fires no schedule on the call: what came
    due off the shifts waits for the next one (D-193). On 10/06 each worker that came in started
    the overdue 18:20 price refresh first and was stopped by the next deploy before the writer
    was given anything."""
    shift_end = datetime(2026, 10, 6, 8, 0, tzinfo=UTC)  # OFF's shift is 07:00-08:00 UTC
    ledger = Ledger()
    worker = Desk(
        start=shift_end - timedelta(milliseconds=50),
        called_at=shift_end + timedelta(milliseconds=20),
        overtime=ledger,
    )
    await asyncio.wait_for(_run(worker, 0.4), timeout=2)
    assert worker.scheduler.passes == 1  # the shift's, still running when it ended
    assert any(worker.dispatched)  # the person's work was looked for on the call
    assert len(ledger.calls) == 1  # and the call ended and was written down


def test_a_call_is_over_when_idle_long_enough_or_at_its_limit():
    call = Call(started=NOON, until=NOON + timedelta(hours=1))
    idle = timedelta(minutes=3)
    assert not call.over(NOON + timedelta(minutes=10), idle)
    call.idle_since = NOON + timedelta(minutes=10)
    assert not call.over(NOON + timedelta(minutes=12), idle)
    assert call.over(NOON + timedelta(minutes=13), idle)
    assert Call(started=NOON, until=NOON + timedelta(hours=1)).over(NOON + timedelta(hours=1), idle)


async def test_overtime_is_kept_by_day_and_limited_by_the_day_and_the_month(db_session):
    """In the database (a deploy does not reset it), split at midnight, in the shifts' zone."""
    taipei = ZoneInfo("Asia/Taipei")
    factory = async_sessionmaker(
        bind=await db_session.connection(),
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    ledger = Overtime(
        factory, day_limit=timedelta(hours=4), month_limit=timedelta(hours=46), zone=taipei
    )
    # year 2099, so no other test's day is ever counted with these
    evening = datetime(2099, 3, 10, 23, 30, tzinfo=taipei)
    await ledger.record(evening, evening + timedelta(hours=1))  # 23:30 to 00:30
    await ledger.record(evening - timedelta(hours=2), evening - timedelta(hours=1))

    ninety = timedelta(hours=1, minutes=30)
    assert await ledger.used(evening) == (ninety, ninety)
    next_day = evening + timedelta(hours=1)
    assert await ledger.used(next_day) == (timedelta(minutes=30), timedelta(hours=2))
    assert await ledger.left(evening) == timedelta(hours=2, minutes=30)  # the day's limit binds

    for day in range(11, 31):  # three hours a day for the rest of March: the month runs out
        await ledger.record(
            datetime(2099, 3, day, 9, tzinfo=taipei), datetime(2099, 3, day, 12, tzinfo=taipei)
        )
    late = datetime(2099, 3, 31, 9, tzinfo=taipei)
    assert await ledger.left(late) == timedelta(0)
    assert await ledger.left(datetime(2099, 4, 1, 9, tzinfo=taipei)) == timedelta(hours=4)
