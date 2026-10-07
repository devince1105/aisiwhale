"""newsroom.refresh_prices a few stocks a run, every five minutes of a shift (D-244)

The refresh asked every stock in one run, Tiingo's 75 seconds apart: some 120 US stocks, two and
a half hours in which no other schedule ran, begun again after every deploy. It now asks a few a
run, each once a day, and remembers in ``price_fetches`` (which takes ``tw`` and ``us`` now)
when each was read. The schedule's row gets the new cron; when it next runs is left as it is.

Revision ID: 0078
Revises: 0077
Create Date: 2026-10-07 19:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0078"
down_revision: str | None = "0077"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

HANDLER = "newsroom.refresh_prices"
CRON = "*/5 7-12 * * 1-5"
BEFORE = "20 7,10 * * 1-5"


def upgrade() -> None:
    op.drop_constraint(op.f("ck_price_fetches_market"), "price_fetches", type_="check")
    op.create_check_constraint(
        op.f("ck_price_fetches_market"), "price_fetches", "market in ('fx', 'crypto', 'tw', 'us')"
    )
    op.execute(
        sa.text("UPDATE schedules SET cron = :cron WHERE handler = :handler").bindparams(
            cron=CRON, handler=HANDLER
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text("UPDATE schedules SET cron = :cron WHERE handler = :handler").bindparams(
            cron=BEFORE, handler=HANDLER
        )
    )
    op.execute("DELETE FROM price_fetches WHERE market IN ('tw', 'us')")
    op.drop_constraint(op.f("ck_price_fetches_market"), "price_fetches", type_="check")
    op.create_check_constraint(
        op.f("ck_price_fetches_market"), "price_fetches", "market in ('fx', 'crypto')"
    )
