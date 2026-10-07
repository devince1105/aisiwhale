"""admin_roles: who may do what in the back office (AD-09, D-234)

ADMIN_EMAILS are owners, from the environment; anybody else an owner lets in has a row here
with one of four roles (owner, editor, finance, viewer). What each role may do is the API's
(autora_api/permissions.py).

Revision ID: 0078
Revises: 0077
Create Date: 2026-10-07 18:30:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0078"
down_revision: str | None = "0077"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "admin_roles",
        sa.Column("reader_id", sa.UUID(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("granted_by", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "role IN ('owner', 'editor', 'finance', 'viewer')",
            name=op.f("ck_admin_roles_role_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["reader_id"], ["readers.id"], name=op.f("fk_admin_roles_reader_id_readers")
        ),
        sa.PrimaryKeyConstraint("reader_id", name=op.f("pk_admin_roles")),
    )


def downgrade() -> None:
    op.drop_table("admin_roles")
