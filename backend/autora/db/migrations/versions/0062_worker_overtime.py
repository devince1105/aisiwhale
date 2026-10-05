"""The office's overtime, one row a day (D-205)

Off its shifts the worker comes in when a person has just done something in the back office, and
that is overtime: limited a day and a month, as 勞基法 limits it. The hours used are kept here so
a deploy does not reset the month's count.

Revision ID: 0062
Revises: 0061
Create Date: 2026-10-05 15:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0062"
down_revision: str | None = "0061"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "worker_overtime",
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("seconds", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("seconds >= 0", name=op.f("ck_worker_overtime_seconds_non_negative")),
        sa.PrimaryKeyConstraint("day", name=op.f("pk_worker_overtime")),
    )


def downgrade() -> None:
    op.drop_table("worker_overtime")
