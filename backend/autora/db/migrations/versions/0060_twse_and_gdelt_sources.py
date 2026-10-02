"""Two more kinds of source: TWSE material announcements and GDELT (D-169)

Revision ID: 0060
Revises: 0059
Create Date: 2026-10-03 06:00:00+00:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0060"
down_revision: str | None = "0059"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD = "kind IN ('rss', 'url_list', 'search_query')"
NEW = "kind IN ('rss', 'url_list', 'search_query', 'twse_announcements', 'gdelt')"


def upgrade() -> None:
    op.drop_constraint(op.f("ck_sources_kind_valid"), "sources", type_="check")
    op.create_check_constraint(op.f("ck_sources_kind_valid"), "sources", NEW)


def downgrade() -> None:
    op.execute("DELETE FROM sources WHERE kind IN ('twse_announcements', 'gdelt')")
    op.drop_constraint(op.f("ck_sources_kind_valid"), "sources", type_="check")
    op.create_check_constraint(op.f("ck_sources_kind_valid"), "sources", OLD)
