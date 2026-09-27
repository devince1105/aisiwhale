"""watchlist_items.position: the reader's own order (D-063)

The lists already kept are numbered in the order they had: when each item was added.

Revision ID: 0051
Revises: 0050
Create Date: 2026-09-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0051"
down_revision: str | None = "0050"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "watchlist_items",
        sa.Column("position", sa.Integer(), server_default="0", nullable=False),
    )
    op.execute(
        """
        UPDATE watchlist_items AS w SET position = numbered.place
        FROM (
            SELECT id, row_number() OVER (PARTITION BY reader_id ORDER BY created_at, id) AS place
            FROM watchlist_items
        ) AS numbered
        WHERE numbered.id = w.id
        """
    )


def downgrade() -> None:
    op.drop_column("watchlist_items", "position")
