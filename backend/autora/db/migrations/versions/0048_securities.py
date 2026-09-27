"""securities, tracked_securities: any Taiwan or US stock (D-061)

Revision ID: 0048
Revises: 0047
Create Date: 2026-09-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0048"
down_revision: str | None = "0047"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "securities",
        sa.Column("market", sa.Text(), nullable=False),
        sa.Column("symbol", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("name_en", sa.Text(), nullable=True),
        sa.Column("exchange", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("market in ('tw', 'us')", name=op.f("ck_securities_market")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_securities")),
        sa.UniqueConstraint("market", "symbol", name=op.f("uq_securities_market_symbol")),
    )
    op.create_index("ix_securities_name", "securities", ["market", "name"], unique=False)
    op.create_table(
        "tracked_securities",
        sa.Column("market", sa.Text(), nullable=False),
        sa.Column("symbol", sa.Text(), nullable=False),
        sa.Column("last_requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("market in ('tw', 'us')", name=op.f("ck_tracked_securities_market")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tracked_securities")),
        sa.UniqueConstraint("market", "symbol", name=op.f("uq_tracked_securities_market_symbol")),
    )


def downgrade() -> None:
    op.drop_table("tracked_securities")
    op.drop_index("ix_securities_name", table_name="securities")
    op.drop_table("securities")
