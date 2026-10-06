"""raw_closes, price_asks, portfolio_stats, and the schedule that fills them (HD-04)

The holdings dashboard's cards (D-217): ``portfolio_stats`` holds each followed 13F filer's
largest holdings, its biggest moves and its simulated one-year return; ``raw_closes`` keeps the
Tiingo closes and split factors the return was checked against, and ``price_asks`` what Tiingo
was asked, so a stretch is asked once.

A company's schedules are made when a source is added or the markets seed runs; the companies
that already follow 13Fs get ``newsroom.refresh_portfolio_stats`` here, due at once, so the
worker's next shift fills the cards.

Revision ID: 0065
Revises: 0064
Create Date: 2026-10-06 13:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0065"
down_revision: str | None = "0064"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEDULE = "newsroom.refresh_portfolio_stats"
CRON = "40 8,11 * * *"


def upgrade() -> None:
    op.create_table(
        "raw_closes",
        sa.Column("symbol", sa.Text(), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("close", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column(
            "split_factor", sa.Numeric(precision=12, scale=6), server_default="1", nullable=False
        ),
        sa.PrimaryKeyConstraint("symbol", "day", name=op.f("pk_raw_closes")),
    )
    op.create_table(
        "portfolio_stats",
        sa.Column("source_id", sa.UUID(), nullable=False),
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("period", sa.Date(), nullable=False),
        sa.Column("filed", sa.Date(), nullable=False),
        sa.Column("long_value_usd", sa.Numeric(precision=20, scale=0), nullable=False),
        sa.Column("holdings", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("moves", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("return_pct", sa.Numeric(precision=12, scale=6), nullable=True),
        sa.Column("return_start", sa.Date(), nullable=True),
        sa.Column("return_through", sa.Date(), nullable=True),
        sa.Column("coverage", sa.Numeric(precision=6, scale=4), nullable=True),
        sa.Column("pending", sa.Integer(), server_default="0", nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["company_id"], ["companies.id"], name=op.f("fk_portfolio_stats_company_id_companies")
        ),
        sa.ForeignKeyConstraint(
            ["source_id"], ["sources.id"], name=op.f("fk_portfolio_stats_source_id_sources")
        ),
        sa.PrimaryKeyConstraint("source_id", name=op.f("pk_portfolio_stats")),
    )
    op.create_table(
        "price_asks",
        sa.Column("symbol", sa.Text(), nullable=False),
        sa.Column("start", sa.Date(), nullable=False),
        sa.Column("end", sa.Date(), nullable=False),
        sa.Column("asked_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("symbol", "start", "end", name=op.f("pk_price_asks")),
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
    op.drop_table("price_asks")
    op.drop_table("portfolio_stats")
    op.drop_table("raw_closes")
