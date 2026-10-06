"""membership_grants, and customers.kind 'comp' (P2)

P2 (D-218, D-228): VIP is given two ways. Bought — P8, not yet — and given by an admin for
internal testing (``admin_comp``). ``membership_grants`` keeps one row a grant, so a membership's
history is not overwritten: ``memberships`` stays the current period that access is decided
from. A comp has no order, payment or ledger row (``payment_id`` is set only for ``payment``),
must say why, and is ended by revoking it — who, when and why written on the row.

``customers.kind`` gains ``comp``: a reader given VIP is a customer the company can point at,
but not a paying one, and the paying count leaves them out.

No price is touched: the catalogue stays what PayUni was applied with (NT$30 a month, D-161;
D-231). Selling stays closed in P2 all the same — the API refuses checkout until P8.

Revision ID: 0069
Revises: 0068
Create Date: 2026-10-06 18:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0069"
down_revision: str | None = "0068"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

KINDS = "'subscriber', 'sponsor', 'client'"


def upgrade() -> None:
    op.create_table(
        "membership_grants",
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("membership_id", sa.UUID(), nullable=False),
        sa.Column("customer_id", sa.UUID(), nullable=False),
        sa.Column("product_id", sa.UUID(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("actor", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("payment_id", sa.UUID(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_by", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("revoke_reason", sa.Text(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(source = 'payment') = (payment_id IS NOT NULL)",
            name=op.f("ck_membership_grants_payment_only_when_paid"),
        ),
        sa.CheckConstraint(
            "source <> 'admin_comp' OR length(btrim(coalesce(reason, ''))) > 0",
            name=op.f("ck_membership_grants_comp_has_a_reason"),
        ),
        sa.CheckConstraint(
            "source IN ('payment', 'admin_comp')", name=op.f("ck_membership_grants_source_valid")
        ),
        sa.CheckConstraint(
            "(revoked_at IS NULL) = (revoked_by IS NULL)"
            " AND (revoked_at IS NULL) = (revoke_reason IS NULL)",
            name=op.f("ck_membership_grants_revocation_complete"),
        ),
        sa.CheckConstraint(
            "expires_at > started_at", name=op.f("ck_membership_grants_expires_after_start")
        ),
        sa.CheckConstraint(
            "revoked_at IS NULL OR revoked_at >= started_at",
            name=op.f("ck_membership_grants_revoked_after_start"),
        ),
        sa.ForeignKeyConstraint(
            ["company_id"], ["companies.id"], name=op.f("fk_membership_grants_company_id_companies")
        ),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customers.id"],
            name=op.f("fk_membership_grants_customer_id_customers"),
        ),
        sa.ForeignKeyConstraint(
            ["membership_id"],
            ["memberships.id"],
            name=op.f("fk_membership_grants_membership_id_memberships"),
        ),
        sa.ForeignKeyConstraint(
            ["payment_id"], ["payments.id"], name=op.f("fk_membership_grants_payment_id_payments")
        ),
        sa.ForeignKeyConstraint(
            ["product_id"], ["products.id"], name=op.f("fk_membership_grants_product_id_products")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_membership_grants")),
    )
    op.create_index(
        op.f("ix_membership_grants_company_id"), "membership_grants", ["company_id"], unique=False
    )
    op.create_index(
        op.f("ix_membership_grants_customer_id"), "membership_grants", ["customer_id"], unique=False
    )
    op.create_index(
        op.f("ix_membership_grants_membership_id"),
        "membership_grants",
        ["membership_id"],
        unique=False,
    )

    op.drop_constraint(op.f("ck_customers_kind_valid"), "customers", type_="check")
    op.create_check_constraint(
        op.f("ck_customers_kind_valid"), "customers", f"kind IN ({KINDS}, 'comp')"
    )


def downgrade() -> None:
    # a comp customer or a grant is history: going back would have to delete it, so it refuses
    comps = op.get_bind().scalar(
        sa.text(
            "SELECT (SELECT count(*) FROM customers WHERE kind = 'comp')"
            " + (SELECT count(*) FROM membership_grants)"
        )
    )
    if comps:
        raise RuntimeError(
            f"{comps} comp customers or membership grants exist; refusing to drop them"
        )
    op.drop_constraint(op.f("ck_customers_kind_valid"), "customers", type_="check")
    op.create_check_constraint(op.f("ck_customers_kind_valid"), "customers", f"kind IN ({KINDS})")
    op.drop_index(op.f("ix_membership_grants_membership_id"), table_name="membership_grants")
    op.drop_index(op.f("ix_membership_grants_customer_id"), table_name="membership_grants")
    op.drop_index(op.f("ix_membership_grants_company_id"), table_name="membership_grants")
    op.drop_table("membership_grants")
