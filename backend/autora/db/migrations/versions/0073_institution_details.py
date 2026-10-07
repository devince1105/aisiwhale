"""thirteenf_filings.scale, institution_details: dollars or thousands, and institutions' pages (HD-10)

13F values have been in dollars since 2023, yet some still file in thousands (T. Rowe Price's
second quarter of 2026: US$1 billion for about 1 trillion). ``scale`` is what a filing's values
are multiplied by to be dollars: 1, or 1000 once its table says so, None while in doubt. A filing
already read whose entries average a million dollars or more is not in doubt (1).

``institution_details`` keeps one filer's quarter worked out from its whole tables — the largest
holdings, the biggest buys and sells, an estimate of what it bought and sold — for 機構排行's 100
largest and for anybody a reader opens. Companies that already follow 13Fs get
``newsroom.refresh_institution_details`` here.

Revision ID: 0073
Revises: 0072
Create Date: 2026-10-07 09:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0073"
down_revision: str | None = "0072"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEDULE = "newsroom.refresh_institution_details"
CRON = "5-59/10 * * * *"


def upgrade() -> None:
    op.add_column("thirteenf_filings", sa.Column("scale", sa.Integer(), nullable=True))
    op.add_column(
        "thirteenf_filings",
        sa.Column("scale_attempts", sa.Integer(), server_default="0", nullable=False),
    )
    op.execute(
        """
        UPDATE thirteenf_filings SET scale = 1
        WHERE read_at IS NOT NULL
          AND NOT (entries >= 10 AND value_usd > 0 AND value_usd < 1000000::numeric * entries)
        """
    )
    op.create_table(
        "institution_details",
        sa.Column("cik", sa.Text(), nullable=False),
        sa.Column("period", sa.Date(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "accessions",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'::text[]"),
            nullable=False,
        ),
        sa.Column("previous_period", sa.Date(), nullable=True),
        sa.Column("in_thousands", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("value_usd", sa.Numeric(precision=20, scale=0), nullable=True),
        sa.Column("stock_value_usd", sa.Numeric(precision=20, scale=0), nullable=True),
        sa.Column("stocks", sa.Integer(), nullable=True),
        sa.Column("previous_stock_value_usd", sa.Numeric(precision=20, scale=0), nullable=True),
        sa.Column("net_bought_usd", sa.Numeric(precision=20, scale=0), nullable=True),
        sa.Column(
            "counts",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "top",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "bought",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "sold",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'ready', 'failed')",
            name=op.f("ck_institution_details_status_valid"),
        ),
        sa.PrimaryKeyConstraint("cik", "period", name=op.f("pk_institution_details")),
    )
    op.create_index(
        "ix_institution_details_queue", "institution_details", ["status", "requested_at"]
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
    op.drop_index("ix_institution_details_queue", table_name="institution_details")
    op.drop_table("institution_details")
    op.drop_column("thirteenf_filings", "scale_attempts")
    op.drop_column("thirteenf_filings", "scale")
