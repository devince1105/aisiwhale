"""readers.watchlist_started_at: a watchlist starts with the site's defaults, once (D-062)

Revision ID: 0049
Revises: 0048
Create Date: 2026-09-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0049"
down_revision: str | None = "0048"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "readers", sa.Column("watchlist_started_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("readers", "watchlist_started_at")
