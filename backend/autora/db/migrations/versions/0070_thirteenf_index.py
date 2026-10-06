"""thirteenf_filings, thirteenf_index_days: every 13F filer's quarter, for 機構排行 (HD-08)

The holdings dashboard's ranking (D-217) is every institution that files a 13F, by the value
its summary page reports. SEC's daily index lists the filings; each one's cover page is read
once, a few hundred a run, and kept here. Companies that already follow 13Fs get
``newsroom.refresh_13f_index`` here, due at once.

Revision ID: 0070
Revises: 0069
Create Date: 2026-10-06 20:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0070"
down_revision: str | None = "0069"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEDULE = "newsroom.refresh_13f_index"
CRON = "*/10 * * * *"


def upgrade() -> None:
    op.create_table(
        "thirteenf_filings",
        sa.Column("accession", sa.Text(), nullable=False),
        sa.Column("cik", sa.Text(), nullable=False),
        sa.Column("company", sa.Text(), nullable=False),
        sa.Column("form", sa.Text(), nullable=False),
        sa.Column("filed", sa.Date(), nullable=False),
        sa.Column("period", sa.Date(), nullable=True),
        sa.Column("manager", sa.Text(), nullable=True),
        sa.Column("amendment", sa.Text(), nullable=True),
        sa.Column("report_type", sa.Text(), nullable=True),
        sa.Column("entries", sa.Integer(), nullable=True),
        sa.Column("value_usd", sa.Numeric(precision=20, scale=0), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.PrimaryKeyConstraint("accession", name=op.f("pk_thirteenf_filings")),
    )
    op.create_index("ix_thirteenf_filings_period", "thirteenf_filings", ["period"])
    op.create_index("ix_thirteenf_filings_cik", "thirteenf_filings", ["cik"])
    op.create_index(
        "ix_thirteenf_filings_unread",
        "thirteenf_filings",
        ["filed"],
        postgresql_where=sa.text("read_at IS NULL"),
    )
    op.create_table(
        "thirteenf_index_days",
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("listed", sa.Integer(), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("day", name=op.f("pk_thirteenf_index_days")),
    )
    op.execute(
        sa.text(
            """
            INSERT INTO schedules (id, company_id, name, cron, timezone, handler, next_run_at)
            SELECT gen_random_uuid(), h.company_id, :name, :cron, 'UTC', :name, now()
            FROM schedules AS h
            WHERE h.name = 'newsroom.refresh_holdings'
              AND NOT EXISTS (
                SELECT 1 FROM schedules AS s WHERE s.company_id = h.company_id AND s.name = :name
              )
            """
        ).bindparams(name=SCHEDULE, cron=CRON)
    )


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM schedules WHERE name = :name").bindparams(name=SCHEDULE))
    op.drop_table("thirteenf_index_days")
    op.drop_index("ix_thirteenf_filings_unread", table_name="thirteenf_filings")
    op.drop_index("ix_thirteenf_filings_cik", table_name="thirteenf_filings")
    op.drop_index("ix_thirteenf_filings_period", table_name="thirteenf_filings")
    op.drop_table("thirteenf_filings")
