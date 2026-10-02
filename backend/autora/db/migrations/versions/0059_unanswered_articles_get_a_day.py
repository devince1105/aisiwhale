"""Articles already waiting for approval get a full day from now (D-156)

From D-156 on, an article's approval that nobody answers by its expiry is approved and the
article published. The ones already waiting were asked under the old rule ("expire and ask
again"), so none of them is published on the day the rule changes: each gets 24 hours from now
— time for the operator to object — or keeps its own deadline if that is later.

Revision ID: 0059
Revises: 0058
Create Date: 2026-10-02 06:00:00+00:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0059"
down_revision: str | None = "0058"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "UPDATE approvals SET expires_at = greatest(expires_at, now() + interval '24 hours')"
        " WHERE state = 'PENDING' AND action = 'approve_article'"
    )


def downgrade() -> None:
    pass  # a later deadline is harmless under either rule
