"""the finance office's agents get their head photos: avatar_key (D-113)

Data only. Each agent of a newsroom company whose avatar_key is still "default" gets its
character's key — the head photo the web shows (``/avatars/<key>.jpg``). The 3D office picks a
figure from avatar_key only when it names one of its own models, which these do not, so the
figures stay as they were. The values are written out here, as in 0054.

Revision ID: 0055
Revises: 0054
Create Date: 2026-09-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0055"
down_revision: str | None = "0054"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NEWSROOM_COMPANIES = "SELECT company_id FROM departments WHERE key = 'newsroom'"

AVATARS = {
    "editor_in_chief": "ada",
    "news_intelligence": "sayla",
    "researcher": "rei",
    "analyst": "mari",
    "writer": "shinobu",
    "editor": "ami",
    "marketing": "chunli",
    "ceo": "tifa",
}


def upgrade() -> None:
    bind = op.get_bind()
    for role, key in AVATARS.items():
        bind.execute(
            sa.text(
                "UPDATE agents SET avatar_key = :key WHERE role = :role AND avatar_key = 'default' "
                f"AND status = 'active' AND company_id IN ({NEWSROOM_COMPANIES})"
            ),
            {"role": role, "key": key},
        )


def downgrade() -> None:
    bind = op.get_bind()
    for role, key in AVATARS.items():
        bind.execute(
            sa.text(
                "UPDATE agents SET avatar_key = 'default' WHERE role = :role AND avatar_key = :key "
                f"AND company_id IN ({NEWSROOM_COMPANIES})"
            ),
            {"role": role, "key": key},
        )
