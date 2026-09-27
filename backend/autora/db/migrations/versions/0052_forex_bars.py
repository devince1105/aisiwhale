"""price_bars for forex pairs and coins, and price_fetches (D-082)

Tiingo's forex and crypto days were kept in the API's memory only: every restart asked for every
pair again. ``price_bars`` now takes markets ``fx`` and ``crypto`` (and six decimals: a euro in
dollars is 1.14325), ``price_fetches`` when each series was last asked for.

Revision ID: 0052
Revises: 0051
Create Date: 2026-09-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0052"
down_revision: str | None = "0051"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PRICES = ("open", "high", "low", "close")


def upgrade() -> None:
    op.drop_constraint(op.f("ck_price_bars_market"), "price_bars", type_="check")
    op.create_check_constraint(
        op.f("ck_price_bars_market"), "price_bars", "market in ('tw', 'us', 'fx', 'crypto')"
    )
    for column in PRICES:
        op.alter_column(
            "price_bars", column, type_=sa.Numeric(18, 6), existing_type=sa.Numeric(18, 4)
        )
    op.create_table(
        "price_fetches",
        sa.Column("market", sa.Text(), nullable=False),
        sa.Column("symbol", sa.Text(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.CheckConstraint("market in ('fx', 'crypto')", name=op.f("ck_price_fetches_market")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_price_fetches")),
        sa.UniqueConstraint("market", "symbol", name=op.f("uq_price_fetches_market_symbol")),
    )


def downgrade() -> None:
    op.drop_table("price_fetches")
    op.execute("DELETE FROM price_bars WHERE market IN ('fx', 'crypto')")
    for column in PRICES:
        op.alter_column(
            "price_bars", column, type_=sa.Numeric(18, 4), existing_type=sa.Numeric(18, 6)
        )
    op.drop_constraint(op.f("ck_price_bars_market"), "price_bars", type_="check")
    op.create_check_constraint(op.f("ck_price_bars_market"), "price_bars", "market in ('tw', 'us')")
