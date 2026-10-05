"""D-192: an idle worker polls the database less and less often, and is quick again with work."""

import asyncio
from datetime import UTC, datetime

from autora.runtime.worker import idle_wait


def test_the_wait_doubles_while_idle_and_snaps_back_with_work():
    waits, wait = [], 1.0
    for busy in (False, False, False, False, False, True, False):
        wait = idle_wait(wait, busy=busy, base=1.0, ceiling=8.0)
        waits.append(wait)
    assert waits == [2.0, 4.0, 8.0, 8.0, 8.0, 1.0, 2.0]


def test_never_faster_than_the_base_pace():
    assert idle_wait(0.1, busy=False, base=1.0, ceiling=8.0) == 1.0
    assert idle_wait(0.2, busy=False, base=0.2, ceiling=0.2) == 0.2  # the browser tests' pace


async def test_an_idle_loop_asks_less_often(monkeypatch):
    from autora.runtime import worker as module

    ticks: list[float] = []

    class Idle:
        poll_interval = 0.01
        idle_poll_interval = 0.08
        worker_id = "idle"
        concurrency = 1
        shifts = None
        _running: dict = {}
        _call = None

        def clock(self):
            return datetime.now(UTC)

        async def tick(self):
            ticks.append(asyncio.get_running_loop().time())
            return 0

        async def shutdown(self):
            pass

    stop = asyncio.Event()
    asyncio.get_running_loop().call_later(0.4, stop.set)
    await module.Worker.run_forever(Idle(), stop)  # type: ignore[arg-type]
    gaps = [b - a for a, b in zip(ticks, ticks[1:], strict=False)]
    assert gaps[0] < 0.05 and max(gaps) >= 0.07  # 0.02, 0.04, then 0.08 between passes
    assert len(ticks) < 0.4 / 0.01 / 2  # far fewer passes than at the base pace
