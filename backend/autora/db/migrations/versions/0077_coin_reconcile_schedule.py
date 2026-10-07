"""coins.reconcile: the Whale Coin ledger checked against itself, daily (P3-C-3)

One row in ``schedules`` — 18:05 every day in Taipei, inside the worker's hours on weekdays and
at weekends (15:00-21:00, 18:00-21:00) — for the handler in ``accounts.coins.reconcile``. It
reads the ledger and logs what it found; it writes nothing and notifies nobody (AD-10 later).

Coins are the site's, not a company's, but a schedule belongs to one: it goes to the oldest
company (aisiwhale in production), and to none on a database that has no company yet. Written
once: a database that already has it keeps the one it has. No table is created or changed.

Revision ID: 0077
Revises: 0076
Create Date: 2026-10-07 17:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0077"
down_revision: str | None = "0076"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEDULE = "coins.reconcile"
CRON = "5 18 * * *"
TIMEZONE = "Asia/Taipei"


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            INSERT INTO schedules (id, company_id, name, cron, timezone, handler, next_run_at)
            SELECT gen_random_uuid(), c.id, :name, :cron, :zone, :name, now()
            FROM (SELECT id FROM companies ORDER BY created_at LIMIT 1) AS c
            WHERE NOT EXISTS (SELECT 1 FROM schedules AS s WHERE s.name = :name)
            """
        ).bindparams(name=SCHEDULE, cron=CRON, zone=TIMEZONE)
    )


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM schedules WHERE name = :name").bindparams(name=SCHEDULE))
