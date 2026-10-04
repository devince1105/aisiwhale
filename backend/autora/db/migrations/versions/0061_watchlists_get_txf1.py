"""Lists made before 台指期 joined the strip get it, after the TAIEX (D-188)

A new watchlist starts as the market strip is (D-062); TXF1 joined the strip on 2026-10-04
(D-179), so lists made before then did not have it. Each that still has the TAIEX gets TXF1 right
after it; one whose reader took the TAIEX off is left as it is.

Revision ID: 0061
Revises: 0060
Create Date: 2026-10-04 06:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from autora.accounts.watchlist import INSERT_AFTER_SQL, insert_after_params

revision: str = "0061"
down_revision: str | None = "0060"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    params = insert_after_params(("market", "TAIEX"), ("market", "TXF1"))
    for statement in INSERT_AFTER_SQL:
        op.execute(sa.text(statement).bindparams(**params))


def downgrade() -> None:
    pass  # a reader may have kept it since: theirs to take off
