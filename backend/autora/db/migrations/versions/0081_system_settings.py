"""system_settings, system_setting_changes: what the back office tunes while everything runs (AD-11)

A value set for one of ``runtime.live_settings``' keys (no row: the environment's), and every
change with what it was before and after and by whom — append-only, by 0002's trigger.

Revision ID: 0081
Revises: 0080
Create Date: 2026-10-07 22:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0081"
down_revision: str | None = "0080"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "system_settings",
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("value", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("updated_by", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("key", name=op.f("pk_system_settings")),
    )
    op.create_table(
        "system_setting_changes",
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("before", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("after", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("actor", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_system_setting_changes")),
    )
    op.create_index("ix_system_setting_changes_key_at", "system_setting_changes", ["key", "at"])
    op.execute(
        "CREATE TRIGGER system_setting_changes_append_only BEFORE UPDATE OR DELETE "
        "ON system_setting_changes FOR EACH ROW EXECUTE FUNCTION autora_forbid_mutation()"
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS system_setting_changes_append_only ON system_setting_changes"
    )
    op.drop_index("ix_system_setting_changes_key_at", table_name="system_setting_changes")
    op.drop_table("system_setting_changes")
    op.drop_table("system_settings")
