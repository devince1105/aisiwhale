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
