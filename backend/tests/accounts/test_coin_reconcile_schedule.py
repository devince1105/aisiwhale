"""P3-C-3: the ledger checked daily — ``coins.reconcile`` logs what it found and changes nothing.

The handler is run the way the scheduler runs it (a session, the schedule, the time it was due);
the scheduler's own clock and claiming are tested in ``tests/runtime``.
"""

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select, text

from autora.accounts import Reader
from autora.accounts.coins import CoinTxn, TxnKind, grant
from autora.accounts.coins.reconcile import RECONCILE_SCHEDULE, schedule_handler
from autora.app import build_scheduler
from autora.runtime.actor import Actor

SYSTEM = Actor.system("reconcile-test")
DUE = datetime(2026, 10, 7, 10, 5, tzinfo=UTC)  # 18:05 in Taipei


async def _reader_with(session, coins: int) -> uuid.UUID:
    reader = Reader(email=f"rc{uuid.uuid4().hex[:12]}@example.com")
    session.add(reader)
    await session.flush()
    await grant(
        session, reader.id, requested=coins, cap=coins, kind=TxnKind.PROMOTION_GRANT,
        idempotency_key=f"promo:rc:{reader.id}", actor=SYSTEM,
    )  # fmt: skip
    return reader.id


async def _txns(session) -> int:
    return await session.scalar(select(func.count()).select_from(CoinTxn))


async def test_a_ledger_that_adds_up_is_logged_as_such_and_left_alone(db_session, caplog):
    await _reader_with(db_session, 40)
    before = await _txns(db_session)
    with caplog.at_level(logging.INFO, logger="autora.accounts.coins.reconcile"):
        await schedule_handler()(db_session, None, DUE)
    (record,) = [r for r in caplog.records if r.name == "autora.accounts.coins.reconcile"]
    assert record.levelno == logging.INFO
    assert "coin ledger reconciles" in record.getMessage()
    assert await _txns(db_session) == before


async def test_a_ledger_that_does_not_is_an_error_line_not_a_failed_schedule(db_session, caplog):
    reader = await _reader_with(db_session, 40)
    nudge = await db_session.begin_nested()
    await db_session.execute(
        text("UPDATE coin_wallets SET balance = balance + 1 WHERE reader_id = :r"), {"r": reader}
    )  # the commit-time check would refuse this; the schedule must still say so on its own
    with caplog.at_level(logging.INFO, logger="autora.accounts.coins.reconcile"):
        await schedule_handler()(db_session, None, DUE)  # does not raise
    await nudge.rollback()
    (record,) = [r for r in caplog.records if r.name == "autora.accounts.coins.reconcile"]
    assert record.levelno == logging.ERROR
    assert "does not reconcile" in record.getMessage()
    assert str(reader) in record.getMessage()


def test_the_worker_s_scheduler_runs_it(committed):
    scheduler = build_scheduler(None, committed, f"test-{uuid.uuid4().hex[:6]}")
    assert RECONCILE_SCHEDULE == "coins.reconcile"
    assert RECONCILE_SCHEDULE in scheduler._handlers
