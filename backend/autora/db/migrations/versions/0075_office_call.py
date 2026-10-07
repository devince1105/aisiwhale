"""When a person last changed something in the back office, written down (D-237)

The API keeps it in memory so the worker's question once a minute off the shifts does not wake
the database (D-205); this one row lets the API's next start remember it, so a deploy does not
lose a call.

Revision ID: 0075
Revises: 0074
Create Date: 2026-10-07 05:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0075"
down_revision: str | None = "0074"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "office_call",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("called_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("id = 1", name=op.f("ck_office_call_one_row")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_office_call")),
    )


def downgrade() -> None:
    op.drop_table("office_call")
