"""portfolio_quarters, portfolio_positions: each 13F source's latest quarters, whole (HD-02)

The holdings dashboard (D-217) computes a simulated one-year return from what each tracked filer
held quarter by quarter, so ``newsroom.holdings.refresh_holdings`` keeps every 13F source's latest
six quarters here: one row a quarter (its filings, when it became known, its total) and one per
position in it. A quarter's positions go with it.

Revision ID: 0063
Revises: 0062
Create Date: 2026-10-06 08:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0063"
down_revision: str | None = "0062"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "portfolio_quarters",
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("source_id", sa.UUID(), nullable=False),
        sa.Column("period", sa.Date(), nullable=False),
        sa.Column("filed", sa.Date(), nullable=False),
        sa.Column("filings", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("total_value_usd", sa.Numeric(precision=20, scale=0), nullable=False),
        sa.Column("in_thousands", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_portfolio_quarters_company_id_companies"),
        ),
        sa.ForeignKeyConstraint(
            ["source_id"], ["sources.id"], name=op.f("fk_portfolio_quarters_source_id_sources")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_portfolio_quarters")),
        sa.UniqueConstraint(
            "source_id", "period", name=op.f("uq_portfolio_quarters_source_id_period")
        ),
    )
    op.create_table(
        "portfolio_positions",
        sa.Column("quarter_id", sa.UUID(), nullable=False),
        sa.Column("cusip", sa.Text(), nullable=False),
        sa.Column("issuer", sa.Text(), nullable=False),
        sa.Column("title_of_class", sa.Text(), nullable=False),
        sa.Column("put_call", sa.Text(), server_default="", nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=20, scale=0), nullable=False),
        sa.Column("value_usd", sa.Numeric(precision=20, scale=0), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["quarter_id"],
            ["portfolio_quarters.id"],
            name=op.f("fk_portfolio_positions_quarter_id_portfolio_quarters"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_portfolio_positions")),
        sa.UniqueConstraint(
            "quarter_id",
            "cusip",
            "put_call",
            "kind",
            name=op.f("uq_portfolio_positions_quarter_id_cusip_put_call_kind"),
        ),
    )


def downgrade() -> None:
    op.drop_table("portfolio_positions")
    op.drop_table("portfolio_quarters")
