"""cusip_symbols: which US ticker a 13F CUSIP is (HD-03)

13F filings name CUSIPs, never tickers; the holdings dashboard's simulated return (D-217) needs
prices, and a price needs a ticker. ``newsroom.cusips`` asks OpenFIGI and keeps the answer here —
one with no common-stock listing too, without a ticker, so it is not asked again for a while.

Revision ID: 0064
Revises: 0063
Create Date: 2026-10-06 11:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0064"
down_revision: str | None = "0063"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "cusip_symbols",
        sa.Column("cusip", sa.Text(), nullable=False),
        sa.Column("symbol", sa.Text(), nullable=True),
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column("security_type", sa.Text(), nullable=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("cusip", name=op.f("pk_cusip_symbols")),
    )


def downgrade() -> None:
    op.drop_table("cusip_symbols")
