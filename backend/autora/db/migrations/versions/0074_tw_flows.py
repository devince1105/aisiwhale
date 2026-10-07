"""tw_flows, tw_flow_reads: Taiwan's three institutional investors, stock by stock (HD-12)

13F is the US; for Taiwan the exchanges publish every trading day each security's net buying by
foreign investors, investment trusts and dealers (三大法人), and its foreign ownership ratio.
``tw_flows`` keeps a day a row a security, some forty trading days; ``tw_flow_reads`` which of a
day's four documents (TWSE's and TPEx's flows and ratios) have been read — none in it, a holiday.
Companies that already follow 13Fs get ``newsroom.refresh_tw_flows`` here.

Revision ID: 0074
Revises: 0073
Create Date: 2026-10-07 13:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0074"
down_revision: str | None = "0073"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEDULE = "newsroom.refresh_tw_flows"
CRON = "*/15 7-13 * * 1-5"


def upgrade() -> None:
    op.create_table(
        "tw_flows",
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("symbol", sa.Text(), nullable=False),
        sa.Column("exchange", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column("foreign_net", sa.BigInteger(), nullable=True),
        sa.Column("trust_net", sa.BigInteger(), nullable=True),
        sa.Column("dealer_net", sa.BigInteger(), nullable=True),
        sa.Column("total_net", sa.BigInteger(), nullable=True),
        sa.Column("foreign_ratio", sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column("foreign_shares", sa.BigInteger(), nullable=True),
        sa.Column("issued_shares", sa.BigInteger(), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("day", "symbol", name=op.f("pk_tw_flows")),
    )
    op.create_index("ix_tw_flows_symbol_day", "tw_flows", ["symbol", "day"])
    op.create_table(
        "tw_flow_reads",
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("rows", sa.Integer(), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("day", "source", name=op.f("pk_tw_flow_reads")),
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
    op.drop_table("tw_flow_reads")
    op.drop_index("ix_tw_flows_symbol_day", table_name="tw_flows")
    op.drop_table("tw_flows")
