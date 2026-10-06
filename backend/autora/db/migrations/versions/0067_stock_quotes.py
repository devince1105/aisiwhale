"""stock_quotes; the holdings dashboard's runs every twenty minutes (HD-04)

Its first version asked every quote and twenty Tiingo stretches, 75 seconds apart, in one run —
and a scheduler handler holds up everything else the worker starts: on its first shift new agent
runs waited half an hour. Now a run asks a few quotes and two stretches, keeps the quotes here,
and comes every twenty minutes; the schedule 0065 made is moved to that.

Revision ID: 0067
Revises: 0066
Create Date: 2026-10-06 16:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0067"
down_revision: str | None = "0066"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEDULE = "newsroom.refresh_portfolio_stats"


def upgrade() -> None:
    op.create_table(
        "stock_quotes",
        sa.Column("symbol", sa.Text(), nullable=False),
        sa.Column("price", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("symbol", name=op.f("pk_stock_quotes")),
    )
    op.execute(
        sa.text("UPDATE schedules SET cron = :cron WHERE name = :name").bindparams(
            cron="*/20 * * * *", name=SCHEDULE
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text("UPDATE schedules SET cron = :cron WHERE name = :name").bindparams(
            cron="40 8,11 * * *", name=SCHEDULE
        )
    )
    op.drop_table("stock_quotes")
