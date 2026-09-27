"""watchlist_items.market may be market: the strip's indices, rate, oil and coins (D-062)

Revision ID: 0050
Revises: 0049
Create Date: 2026-09-27
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0050"
down_revision: str | None = "0049"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(op.f("ck_watchlist_items_market"), "watchlist_items", type_="check")
    op.create_check_constraint(
        op.f("ck_watchlist_items_market"), "watchlist_items", "market in ('tw', 'us', 'market')"
    )


def downgrade() -> None:
    op.execute("DELETE FROM watchlist_items WHERE market = 'market'")
    op.drop_constraint(op.f("ck_watchlist_items_market"), "watchlist_items", type_="check")
    op.create_check_constraint(
        op.f("ck_watchlist_items_market"), "watchlist_items", "market in ('tw', 'us')"
    )
