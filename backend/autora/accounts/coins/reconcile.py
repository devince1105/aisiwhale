"""Checking the whole ledger against itself (P3-A, blueprint §8.3). Reads only.

What is checked, each a sum that must come out exact:

1. every entry, across every account, sums to zero;
2. each wallet equals its reader's entries, and the balance after its last transaction, and is
   never negative;
3. ISSUANCE is minus every grant, BURN is minus every spend and refund, ADJUSTMENT is minus
   every adjustment;
4. each refund gives back exactly the spend it reverses;
5. a transaction that moves coins has two entries, one that moves none has none.

The commit-time trigger already holds each transaction to most of this; this is the daily look
across all of them, and the numbers the metrics (D-229) start from.

Run daily by the ``coins.reconcile`` schedule (P3-C-3, migration 0077; 18:05 in Taipei) and each
time the back office's coins page opens. The schedule only logs: an ``info`` line with the totals
when the ledger adds up, an ``error`` line with every problem when it does not. It never raises,
so a finding is not mistaken for the schedule failing; nothing is stored and nobody is notified
until the back office has notifications (AD-10).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from autora.accounts.coins.models import CoinAccount, CoinEntry, CoinTxn, SystemAccount, TxnKind

if TYPE_CHECKING:
    from autora.db.models import Schedule

log = logging.getLogger(__name__)

RECONCILE_SCHEDULE = "coins.reconcile"


@dataclass
class Reconciliation:
    problems: list[str] = field(default_factory=list)
    totals: dict[str, int] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.problems


async def reconcile(session: AsyncSession) -> Reconciliation:
    report = Reconciliation()

    total = await session.scalar(select(func.coalesce(func.sum(CoinEntry.amount), 0)))
    report.totals["entries"] = int(total)
    if total != 0:
        report.problems.append(f"all entries sum to {total}, not 0")

    wallets = await session.execute(
        text(
            """
            SELECT w.reader_id, w.balance,
                   coalesce((SELECT sum(e.amount) FROM coin_entries e
                             WHERE e.account_id = w.account_id), 0) AS ledger,
                   (SELECT t.balance_after FROM coin_txns t WHERE t.id = w.last_txn_id) AS last
            FROM coin_wallets w
            """
        )
    )
    held = 0
    for reader_id, balance, ledger, last in wallets:
        held += balance
        if balance < 0:
            report.problems.append(f"wallet of reader {reader_id} is negative: {balance}")
        if balance != ledger:
            report.problems.append(f"wallet of reader {reader_id} says {balance}, entries {ledger}")
        if last is not None and last != balance:
            report.problems.append(
                f"wallet of reader {reader_id} says {balance}, its last transaction {last}"
            )
    report.totals["held_by_readers"] = held

    by_kind = dict(
        (
            await session.execute(
                select(CoinTxn.kind, func.coalesce(func.sum(CoinTxn.amount), 0)).group_by(
                    CoinTxn.kind
                )
            )
        ).all()
    )
    kind = {k: int(by_kind.get(k.value, 0)) for k in TxnKind}
    system = dict(
        (
            await session.execute(
                select(CoinAccount.system_key, func.coalesce(func.sum(CoinEntry.amount), 0))
                .select_from(CoinAccount)
                .outerjoin(CoinEntry, CoinEntry.account_id == CoinAccount.id)
                .where(CoinAccount.system_key.is_not(None))
                .group_by(CoinAccount.system_key)
            )
        ).all()
    )
    expected = {
        SystemAccount.ISSUANCE: -(kind[TxnKind.MONTHLY_GRANT] + kind[TxnKind.PROMOTION_GRANT]),
        SystemAccount.BURN: -(kind[TxnKind.SPEND] + kind[TxnKind.REFUND]),
        SystemAccount.ADJUSTMENT: -kind[TxnKind.ADMIN_ADJUSTMENT],
    }
    for account, should in expected.items():
        actual = int(system.get(account.value, 0))
        report.totals[account.value] = actual
        if actual != should:
            report.problems.append(f"{account} holds {actual}, its transactions say {should}")

    refunds = await session.execute(
        text(
            """
            SELECT r.id FROM coin_txns r JOIN coin_txns s ON s.id = r.reverses_txn_id
            WHERE r.kind = 'REFUND'
              AND (s.kind <> 'SPEND' OR s.reader_id <> r.reader_id OR s.amount <> -r.amount)
            """
        )
    )
    for (refund_id,) in refunds:
        report.problems.append(f"refund {refund_id} does not give back its spend in full")

    legs = await session.execute(
        text(
            """
            SELECT t.id, t.amount, count(e.id) AS legs
            FROM coin_txns t LEFT JOIN coin_entries e ON e.txn_id = t.id
            GROUP BY t.id, t.amount
            HAVING count(e.id) <> CASE WHEN t.amount = 0 THEN 0 ELSE 2 END
            """
        )
    )
    for txn_id, amount, count in legs:
        report.problems.append(f"transaction {txn_id} moves {amount} with {count} entries")

    return report


def schedule_handler():
    """The ``coins.reconcile`` handler: check the ledger, say what was found, change nothing."""

    async def handler(session: AsyncSession, schedule: Schedule, scheduled_for: datetime) -> None:
        report = await reconcile(session)
        if report.ok:
            log.info("coin ledger reconciles: %s", report.totals)
        else:
            log.error(
                "coin ledger does not reconcile (%d problems): %s; totals %s",
                len(report.problems),
                "; ".join(report.problems),
                report.totals,
            )

    return handler
