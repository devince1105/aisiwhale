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

revision: str = "0061"
down_revision: str | None = "0060"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


INSERT_AFTER_SQL = (
    # make room after ``after`` on every list that has it and has not ``new`` yet
    """
    UPDATE watchlist_items AS w SET position = w.position + 1
    FROM watchlist_items AS a
    WHERE a.market = :after_market AND a.symbol = :after_symbol
      AND w.reader_id = a.reader_id AND w.position > a.position
      AND NOT EXISTS (
        SELECT 1 FROM watchlist_items AS n
        WHERE n.reader_id = a.reader_id AND n.market = :new_market AND n.symbol = :new_symbol
      )
    """,
    # and put it there
    """
    INSERT INTO watchlist_items (id, reader_id, market, symbol, position, created_at)
    SELECT gen_random_uuid(), a.reader_id, :new_market, :new_symbol, a.position + 1, now()
    FROM watchlist_items AS a
    WHERE a.market = :after_market AND a.symbol = :after_symbol
      AND NOT EXISTS (
        SELECT 1 FROM watchlist_items AS n
        WHERE n.reader_id = a.reader_id AND n.market = :new_market AND n.symbol = :new_symbol
      )
    """,
)
"""A new default goes onto the lists made before it (D-188): right after the figure it follows,
on every list that still has that figure — a reader who took it off has made the list their own.
Run once, by a migration; a list that has it already is left as it is."""


def insert_after_params(after: tuple[str, str], new: tuple[str, str]) -> dict[str, str]:
    return {
        "after_market": after[0],
        "after_symbol": after[1],
        "new_market": new[0],
        "new_symbol": new[1],
    }


def upgrade() -> None:
    params = insert_after_params(("market", "TAIEX"), ("market", "TXF1"))
    for statement in INSERT_AFTER_SQL:
        op.execute(sa.text(statement).bindparams(**params))


def downgrade() -> None:
    pass  # a reader may have kept it since: theirs to take off
