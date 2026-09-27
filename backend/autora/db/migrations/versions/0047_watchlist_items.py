"""watchlist_items: a reader's own watchlist (D-060)

Revision ID: 0047
Revises: 0046
Create Date: 2026-09-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0047"
down_revision: str | None = "0046"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "watchlist_items",
        sa.Column("reader_id", sa.UUID(), nullable=False),
        sa.Column("market", sa.Text(), nullable=False),
        sa.Column("symbol", sa.Text(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("market in ('tw', 'us')", name=op.f("ck_watchlist_items_market")),
        sa.ForeignKeyConstraint(
            ["reader_id"],
            ["readers.id"],
            name=op.f("fk_watchlist_items_reader_id_readers"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_watchlist_items")),
        sa.UniqueConstraint(
            "reader_id", "market", "symbol", name=op.f("uq_watchlist_items_reader_id_market_symbol")
        ),
    )
    op.create_index(
        op.f("ix_watchlist_items_reader_id"), "watchlist_items", ["reader_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_watchlist_items_reader_id"), table_name="watchlist_items")
    op.drop_table("watchlist_items")
