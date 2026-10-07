"""admin_prefs and admin.approvals_digest: the back office tells people what waits (AD-10, D-234)

``admin_prefs``: what an admin asked for — for now, whether the daily email of approvals waiting
comes to them (no row: it does). One row in ``schedules``, ``admin.approvals_digest`` at 15:05 in
Taipei, when the worker's weekday shift starts (a weekend's comes when that shift does), for the
handler in ``accounts.admin_digest``. Like 0077's, it belongs to the oldest company and is written
once.

Revision ID: 0080
Revises: 0079
Create Date: 2026-10-07 20:30:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0080"
down_revision: str | None = "0079"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEDULE = "admin.approvals_digest"
CRON = "5 15 * * *"
TIMEZONE = "Asia/Taipei"


def upgrade() -> None:
    op.create_table(
        "admin_prefs",
        sa.Column("reader_id", sa.UUID(), nullable=False),
        sa.Column("approvals_digest", sa.Boolean(), server_default="true", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["reader_id"], ["readers.id"], name=op.f("fk_admin_prefs_reader_id_readers")
        ),
        sa.PrimaryKeyConstraint("reader_id", name=op.f("pk_admin_prefs")),
    )
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
    op.drop_table("admin_prefs")
