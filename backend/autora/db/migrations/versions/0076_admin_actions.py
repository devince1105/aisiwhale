"""admin_actions: what people did in the back office (AD-06, D-234)

One row for every request that changes something through the back office's door — an admin
signed in, or the operator token — written by the API: who, when, which route with which ids,
what was sent (secrets masked), and how it ended. Append-only, by the same trigger as the ledger
and the FSM audit (0002).

Revision ID: 0076
Revises: 0075
Create Date: 2026-10-07 15:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0076"
down_revision: str | None = "0075"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "admin_actions",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("actor", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("method", sa.Text(), nullable=False),
        sa.Column("route", sa.Text(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("target_type", sa.Text(), nullable=True),
        sa.Column("target_id", sa.Text(), nullable=True),
        sa.Column("company_id", sa.UUID(), nullable=True),
        sa.Column("status", sa.Integer(), nullable=False),
        sa.Column("input", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("ip", sa.Text(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["company_id"], ["companies.id"], name=op.f("fk_admin_actions_company_id_companies")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_admin_actions")),
    )
    op.create_index("ix_admin_actions_created", "admin_actions", ["created_at"])
    op.create_index(
        "ix_admin_actions_company_created", "admin_actions", ["company_id", "created_at"]
    )
    op.create_index("ix_admin_actions_target", "admin_actions", ["target_type", "target_id"])
    # who did what is never edited afterwards (autora_forbid_mutation is 0002's)
    op.execute(
        "CREATE TRIGGER admin_actions_append_only BEFORE UPDATE OR DELETE ON admin_actions "
        "FOR EACH ROW EXECUTE FUNCTION autora_forbid_mutation()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS admin_actions_append_only ON admin_actions")
    op.drop_index("ix_admin_actions_target", table_name="admin_actions")
    op.drop_index("ix_admin_actions_company_created", table_name="admin_actions")
    op.drop_index("ix_admin_actions_created", table_name="admin_actions")
    op.drop_table("admin_actions")
