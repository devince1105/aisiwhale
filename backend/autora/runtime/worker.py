"""The worker loop: claims tasks for agents and runs them; keeps the runtime healthy (T-213).

One worker process runs this loop. Several processes can run side by side: every claim is a
``FOR UPDATE SKIP LOCKED`` on the task queue and every agent has at most one open run (DB
index), so they never step on each other.

Each tick:
- **maintenance** (every ``maintenance_interval``): reclaim expired leases (crashed or stalled
  workers), expire overdue approvals, plus whatever ``maintenance_jobs`` the composition root
  added (Phase 6 moves the company's cycle along there — the runtime does not know what a cycle
  is). Each job commits on its own; one failing does not stop the others or the loop.
- **schedules** (D-237): the due ones are fired beside the passes, never inside them — one can
  take hours (the price refresh asks Tiingo for each tracked US stock 75 seconds apart), and
  inside a pass it held up every task, the end of the shift and the answer to a call. One
  scheduler pass at a time; none on a call (D-205), so what came due off the shifts waits for
  the next one (D-193).
- **services** (T-514): run the READY service tasks (workflow steps no agent runs, e.g. approve
  and publish an article) through their handlers, each in its own transaction.
- **dispatch**: for every active agent whose role has a behavior and that this worker is not
  already running, try to claim its next task (or resume its approved run) and start the run as
  an asyncio task, up to ``concurrency`` runs at once.

There is no event dispatcher yet: nothing in Phase 2 reacts to events asynchronously (workflow
propagation happens inside the task transaction). It arrives with the first event handler.

Shutdown (``stop`` set): no new claims; in-flight runs get ``grace`` seconds to finish, then are
cancelled. Their leases expire and another worker re-runs them, so a hard kill is also safe.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from autora.db.models import ActivityState, Agent, AgentActivity, AgentStatus
from autora.runtime.agent_runner import AgentRunner, RunOutcome
from autora.runtime.approvals import ApprovalService
from autora.runtime.oncall import AskForCall, Call, Overtime
from autora.runtime.scheduler import Scheduler
from autora.runtime.services import ServiceDispatcher
from autora.runtime.shifts import Shifts
from autora.runtime.task_manager import AgentBusy, Claim, TaskManager

log = logging.getLogger("autora.worker")

CLOCK_SKEW = timedelta(seconds=5)
"""How far the worker's clock and the API's may disagree (D-205)."""

MaintenanceJob = Callable[[AsyncSession], Awaitable[None]]
"""A periodic job the worker runs in its own transaction and commits (see ``maintenance_jobs``)."""


def idle_wait(previous: float, *, busy: bool, base: float, ceiling: float) -> float:
    """How long the worker waits before its next pass (D-192): ``base`` while there is work,
    doubling from the last wait while there is none, never above ``ceiling``."""
    return base if busy else min(ceiling, max(base, previous * 2))


@dataclass
class Worker:
    worker_id: str
    session_factory: async_sessionmaker[AsyncSession]
    task_manager: TaskManager
    runner: AgentRunner
    approvals: ApprovalService
    scheduler: Scheduler | None = None
    services: ServiceDispatcher | None = None
    concurrency: int = 4
    poll_interval: float = 1.0
    shifts: Shifts | None = None
    """Office hours (D-193): outside them, no new work and — once what runs has finished — no
    query at all until the next shift. None: always at work."""
    on_call: AskForCall | None = None
    """Off duty, asked every ``call_poll_interval`` whether a person has just acted in the back
    office (D-205). If so the worker comes in, works until nothing is left, and goes home again.
    The question goes to the API, never the database. None: the shifts only."""
    overtime: Overtime | None = None
    """What a call may use and what it used (勞基法: a day's and a month's limit). None: no
    limit but ``call_limit`` per call."""
    call_poll_interval: float = 60.0
    call_idle: float = 180.0
    """On call, seconds with nothing to do before the worker goes home."""
    call_limit: float = 3600.0
    """The longest one call lasts, in seconds."""
    idle_poll_interval: float = 8.0
    """Idle, the loop slows down (D-192): a pass that finds nothing to do and nothing running waits
    twice as long as the last one, up to this; any work brings it back to ``poll_interval``. Every
    pass reads every free agent and their claimable tasks from the database, and the database's
    network transfer is metered: a second-by-second loop over an idle office was most of it."""
    maintenance_interval: float = 15.0
    grace: float = 30.0
    company_ids: frozenset[uuid.UUID] | None = None
    """Only run agents of these companies (None: all). Lets tests and shards share a database."""
    maintenance_jobs: list[tuple[str, MaintenanceJob]] = field(default_factory=list)
    """Extra periodic jobs, ``(name, job)``, registered by ``app.py``: anything a higher layer
    needs done on a schedule the runtime cannot name. Each runs in its own transaction and its
    failure is logged, never raised."""
    clock: Callable[[], datetime] = field(default=lambda: datetime.now(UTC))
    on_outcome: Callable[[RunOutcome], Awaitable[None]] | None = None
    _running: dict[uuid.UUID, asyncio.Task[RunOutcome | None]] = field(default_factory=dict)
    _schedules: asyncio.Task[list[str]] | None = None
    """The scheduler's pass, running beside the worker's (D-237)."""
    _last_maintenance: datetime | None = None
    _call: Call | None = None
    _answered: datetime | None = None
    """The latest call taken (D-205): one call is answered once."""
    _covered_until: datetime | None = None
    """Up to when the worker has been at work: what a person did before that, it has seen."""
    _clocked_out: bool = False

    # --- loop ------------------------------------------------------------------------------

    async def run_forever(self, stop: asyncio.Event) -> None:
        log.info("worker %s started (concurrency=%d)", self.worker_id, self.concurrency)
        wait = self.poll_interval
        while not stop.is_set():
            if self.shifts is not None and not await self._at_work():
                await self._off_duty(stop)
                wait = self.poll_interval
                continue
            self._clocked_out = False
            # a little before the pass begins: the two machines' clocks need not agree exactly
            self._covered_until = self.clock() - CLOCK_SKEW
            handled = 0
            try:
                handled = await self.tick()
            except Exception:  # noqa: BLE001 - a transient DB error must not end the process
                log.exception("worker tick failed")
            busy = handled > 0 or bool(self._running)
            if self._call is not None:
                self._call.idle_since = None if busy else (self._call.idle_since or self.clock())
            wait = idle_wait(
                wait, busy=busy, base=self.poll_interval, ceiling=self.idle_poll_interval
            )
            try:
                await asyncio.wait_for(stop.wait(), timeout=wait)
            except TimeoutError:
                pass
        if self._call is not None:  # stopped on a call — a deploy: the time in is still overtime,
            await self._end_call(self.clock())  # written before the grace Render's kill may cut
        await self.shutdown()

    async def _at_work(self) -> bool:
        """On a shift, or on a call that is not over (D-205). A call ends when it is done, at its
        limit, or when a shift begins; its time is written down as overtime then."""
        assert self.shifts is not None
        now = self.clock()
        on_shift = self.shifts.on_duty(now)
        if self._call is not None and (
            on_shift or self._call.over(now, timedelta(seconds=self.call_idle))
        ):
            await self._end_call(now)
        return on_shift or self._call is not None

    async def _off_duty(self, stop: asyncio.Event) -> None:
        """Clocked out (D-193): let what runs finish, then wait for the next shift without a
        query — or, on call (D-205), until a person does something in the back office. A schedule
        still firing from the shift goes on beside this until it is done (D-237): it does not
        keep the worker from answering a call."""
        if self._running:
            await asyncio.wait(list(self._running.values()), timeout=self.poll_interval)
            return
        assert self.shifts is not None
        now = self.clock()
        start = self.shifts.next_start(now)
        if not self._clocked_out:
            on_call = " (on call)" if self.on_call is not None else ""
            log.info("worker %s off duty until %s%s", self.worker_id, start.isoformat(), on_call)
            self._clocked_out = True
        # woken at most hourly, so a clock that jumped (a sleeping laptop) is not trusted for days
        ceiling = self.call_poll_interval if self.on_call is not None else 3600.0
        seconds = min(ceiling, max(1.0, (start - now).total_seconds()))
        try:
            await asyncio.wait_for(stop.wait(), timeout=seconds)
        except TimeoutError:
            pass
        if self.on_call is not None and not stop.is_set():
            await self._answer()

    async def _answer(self) -> None:
        """Has a person acted since the worker last worked? Then it comes in — if the day's and
        the month's overtime allow (D-205)."""
        assert self.on_call is not None and self.shifts is not None
        called = await self.on_call()
        now = self.clock()
        if called is None or self.shifts.on_duty(now):
            return
        limit = timedelta(seconds=self.call_limit)
        # a worker just started has seen nothing: it answers a call of the last hour, not older
        seen = max(
            (t for t in (self._answered, self._covered_until) if t is not None),
            default=now - limit,
        )
        if called <= seen:
            return
        self._answered = called
        left = limit
        if self.overtime is not None:
            try:
                left = min(limit, await self.overtime.left(now))
            except Exception:  # noqa: BLE001 - no record of the hours, no overtime
                log.exception("cannot read the overtime used; not coming in")
                return
        if left <= timedelta(0):
            log.info(
                "worker %s: a person acted at %s, but the overtime allowed is used up",
                self.worker_id, called.isoformat(),
            )  # fmt: skip
            return
        self._call = Call(started=now, until=now + left)
        log.info(
            "worker %s on call: a person acted at %s (at most %s of overtime)",
            self.worker_id, called.isoformat(), left,
        )  # fmt: skip

    async def _end_call(self, now: datetime) -> None:
        call, self._call = self._call, None
        assert call is not None
        log.info("worker %s: call over after %s", self.worker_id, now - call.started)
        if self.overtime is not None:
            try:
                await self.overtime.record(call.started, now)
            except Exception:  # noqa: BLE001 - the work is done; only the record is lost
                log.exception("cannot write down the overtime of a call")

    async def tick(self, *, wait_for_schedules: bool = False) -> int:
        """One pass: maintenance if due (and the due schedules set off beside it, D-237), service
        steps, then claim and start runs. ``wait_for_schedules``: the schedules fire before the
        rest, as drains and tests need. Returns the service steps handled plus the runs started."""
        now = self.clock()
        if self._last_maintenance is None or now - self._last_maintenance >= timedelta(
            seconds=self.maintenance_interval
        ):
            await self.maintain()
            self._fire_schedules()
            self._last_maintenance = now
        if wait_for_schedules and self._schedules is not None:
            await self._schedules
        handled = 0
        if self.services is not None:
            try:
                handled = await self.services.dispatch()
            except Exception:  # noqa: BLE001
                log.exception("service dispatch failed")
        return handled + await self.dispatch()

    async def run_until_idle(self, max_ticks: int = 1000) -> None:
        """Tick until nothing is running and nothing can be claimed (tests, one-off drains)."""
        for _ in range(max_ticks):
            started = await self.tick(wait_for_schedules=True)
            if not self._running:
                if started == 0:
                    return
                continue
            await asyncio.wait(list(self._running.values()), return_when=asyncio.FIRST_COMPLETED)
        raise RuntimeError(f"worker not idle after {max_ticks} ticks")

    async def shutdown(self) -> None:
        """In-flight runs and schedules get ``grace`` seconds; a schedule cut short rolls back and
        is fired again once its lease expires."""
        started = [*self._running.values()]
        if self._schedules is not None and not self._schedules.done():
            started.append(self._schedules)
        if not started:
            return
        log.info("waiting up to %.0fs for %d run(s) and schedule(s)", self.grace, len(started))
        _, pending = await asyncio.wait(started, timeout=self.grace)
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)

    # --- maintenance -----------------------------------------------------------------------

    async def maintain(self) -> None:
        async def reap(session: AsyncSession) -> None:
            reaped = await self.task_manager.reap_expired_leases(session)
            if reaped:
                log.warning("reclaimed %d expired lease(s): %s", len(reaped), reaped)

        async def expire(session: AsyncSession) -> None:
            expired = await self.approvals.expire_due(session)
            if expired:
                log.info("expired %d approval(s)", len(expired))

        for name, job in [
            ("reap_leases", reap),
            ("expire_approvals", expire),
            *self.maintenance_jobs,
        ]:
            try:
                async with self.session_factory() as session:
                    await job(session)
                    await session.commit()
            except Exception:  # noqa: BLE001
                log.exception("maintenance job %s failed", name)

    def _fire_schedules(self) -> None:
        """Set off the scheduler's pass beside the worker's (D-237), unless one is still going —
        or the worker is on a call (D-205): it came in for what a person did, and the schedules
        that came due off the shifts wait for the next one (D-193)."""
        if self.scheduler is None or self._call is not None:
            return
        if self._schedules is not None and not self._schedules.done():
            return
        scheduler = self.scheduler

        async def fire() -> list[str]:
            try:
                return await scheduler.tick()
            except Exception:  # noqa: BLE001
                log.exception("scheduler tick failed")
                return []

        self._schedules = asyncio.create_task(fire(), name="schedules")

    # --- dispatch --------------------------------------------------------------------------

    async def dispatch(self) -> int:
        started = 0
        for agent in await self._candidates():
            if len(self._running) >= self.concurrency:
                break
            claim = await self._claim(agent)
            if claim is None:
                continue
            self._running[agent.id] = asyncio.create_task(
                self._run(claim), name=f"run-{claim.run.id}"
            )
            started += 1
        return started

    async def _candidates(self) -> list[Agent]:
        roles = self.runner.behaviors.roles()
        if not roles:
            return []
        async with self.session_factory() as session:
            agents = (
                await session.scalars(
                    select(Agent)
                    .join(AgentActivity, AgentActivity.agent_id == Agent.id)
                    .where(
                        Agent.status == AgentStatus.ACTIVE,
                        Agent.role.in_(roles),
                        AgentActivity.state != ActivityState.PAUSED,
                        *(
                            [Agent.company_id.in_(self.company_ids)]
                            if self.company_ids is not None
                            else []
                        ),
                    )
                    .order_by(Agent.created_at)
                )
            ).all()
        return [a for a in agents if a.id not in self._running]

    async def _claim(self, agent: Agent) -> Claim | None:
        try:
            async with self.session_factory() as session:
                claim = await self.task_manager.claim_next(session, agent, self.worker_id)
                await session.commit()
        except AgentBusy:
            return None  # its run is waiting for approval, or another worker runs it
        return claim

    async def _run(self, claim: Claim) -> RunOutcome | None:
        try:
            outcome = await self.runner.run(claim)
            log.info(
                "run %s (%s, task %s attempt %d): %s%s",
                claim.run.id,
                claim.agent.role,
                claim.task.name,
                claim.task.attempt,
                outcome.status,
                f" {outcome.error_class}: {outcome.message}" if outcome.error_class else "",
            )
            if self.on_outcome is not None:
                await self.on_outcome(outcome)
            return outcome
        except Exception:  # noqa: BLE001 - the runner already handles work failures
            log.exception("run %s crashed", claim.run.id)
            return None
        finally:
            self._running.pop(claim.agent.id, None)
