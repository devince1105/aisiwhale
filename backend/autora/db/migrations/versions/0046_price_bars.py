"""price_bars: daily prices for the stock pages' charts (D-059)

Revision ID: 0046
Revises: 0045
Create Date: 2026-09-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0046"
down_revision: str | None = "0045"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "price_bars",
        sa.Column("market", sa.Text(), nullable=False),
        sa.Column("symbol", sa.Text(), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("open", sa.Numeric(18, 4), nullable=False),
        sa.Column("high", sa.Numeric(18, 4), nullable=False),
        sa.Column("low", sa.Numeric(18, 4), nullable=False),
        sa.Column("close", sa.Numeric(18, 4), nullable=False),
        sa.Column("volume", sa.Numeric(20, 0), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("market in ('tw', 'us')", name=op.f("ck_price_bars_market")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_price_bars")),
        sa.UniqueConstraint(
            "market", "symbol", "day", name=op.f("uq_price_bars_market_symbol_day")
        ),
    )


def downgrade() -> None:
    op.drop_table("price_bars")
