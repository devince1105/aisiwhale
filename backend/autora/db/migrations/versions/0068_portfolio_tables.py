"""portfolio_stats.positions, .stretches: the person page's table and chart (HD-05)

The holdings dashboard's person page (D-217) shows every holding of the latest quarter against
the one before, and the simulated return quarter by quarter. Both are worked out with the card,
by the same run (a holding that may have split waits for Tiingo there too), and kept with it.

Revision ID: 0068
Revises: 0067
Create Date: 2026-10-06 17:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0068"
down_revision: str | None = "0067"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for column in ("positions", "stretches"):
        op.add_column(
            "portfolio_stats",
            sa.Column(
                column,
                postgresql.JSONB(astext_type=sa.Text()),
                server_default=sa.text("'[]'::jsonb"),
                nullable=False,
            ),
        )


def downgrade() -> None:
    op.drop_column("portfolio_stats", "stretches")
    op.drop_column("portfolio_stats", "positions")
