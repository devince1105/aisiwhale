"""payment_events: every payment notification, kept before it is dealt with (P2)

P2 (``logs/platform/18_MONETIZATION_BLUEPRINT.md`` §13): a provider's notification is written
down first, in its own transaction — the form as posted, what the envelope said once opened, and
when — and then dealt with; how that went (``outcome``, ``error``, the order and the payment) is
filled in after. A notification that fails is still on record, for whoever has to work out what
happened, and can be replayed from it.

No price, order or payment is touched. Selling stays closed (D-231).

Revision ID: 0071
Revises: 0070
Create Date: 2026-10-06 21:30:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0071"
down_revision: str | None = "0070"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OUTCOMES = (
    "'received', 'settled', 'repeated', 'unpaid', 'ignored', 'refused', 'unreadable', 'error'"
)


def upgrade() -> None:
    op.create_table(
        "payment_events",
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("fields", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("mer_trade_no", sa.Text(), nullable=True),
        sa.Column("external_ref", sa.Text(), nullable=True),
        sa.Column("trade_status", sa.Text(), nullable=True),
        sa.Column("amount", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("outcome", sa.Text(), server_default="received", nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("order_id", sa.UUID(), nullable=True),
        sa.Column("payment_id", sa.UUID(), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            f"outcome IN ({OUTCOMES})", name=op.f("ck_payment_events_outcome_valid")
        ),
        sa.CheckConstraint(
            "provider ~ '^[a-z][a-z0-9_]*$'", name=op.f("ck_payment_events_provider_format")
        ),
        sa.ForeignKeyConstraint(
            ["order_id"], ["orders.id"], name=op.f("fk_payment_events_order_id_orders")
        ),
        sa.ForeignKeyConstraint(
            ["payment_id"], ["payments.id"], name=op.f("fk_payment_events_payment_id_payments")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_payment_events")),
    )
    op.create_index(
        op.f("ix_payment_events_order_id"), "payment_events", ["order_id"], unique=False
    )
    op.create_index(
        "ix_payment_events_provider_mer_trade_no",
        "payment_events",
        ["provider", "mer_trade_no"],
        unique=False,
    )


def downgrade() -> None:
    # a notification that was received is a record: going back would have to delete it
    kept = op.get_bind().scalar(sa.text("SELECT count(*) FROM payment_events"))
    if kept:
        raise RuntimeError(f"{kept} payment events exist; refusing to drop them")
    op.drop_index("ix_payment_events_provider_mer_trade_no", table_name="payment_events")
    op.drop_index(op.f("ix_payment_events_order_id"), table_name="payment_events")
    op.drop_table("payment_events")
