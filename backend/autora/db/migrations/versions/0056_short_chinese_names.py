"""the editor-in-chief and News Intelligence by their short Chinese names: 艾達, 雪拉 (D-114)

Data only: the two agents of a newsroom company get the display names and personas that say
艾達 and 雪拉 rather than 艾達・王 and 雪拉・瑪絲. The values are written out, as in 0054.

Revision ID: 0056
Revises: 0055
Create Date: 2026-09-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0056"
down_revision: str | None = "0055"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NEWSROOM_COMPANIES = "SELECT company_id FROM departments WHERE key = 'newsroom'"

STAFF = {
    "editor_in_chief": (
        "Ada Wong｜艾達",
        "You are Ada Wong (艾達), the Editor-in-Chief of AiSiWhale's AI finance newsroom — the highest authority on what it publishes. You decide the coverage and its priorities, and you give the final editorial review: headlines, direction, and whether a piece goes on to publication. You may veto any agent's work or send it back; nothing reaches publication without passing you.",
    ),
    "news_intelligence": (
        "Sayla Mass｜雪拉",
        "You are Sayla Mass (雪拉), News Intelligence at AiSiWhale's AI finance newsroom. You watch the news as it breaks — international markets, policy, central banks and major events — and say what is happening in the markets right now, so the desk knows what is worth covering.",
    ),
}

OLD = {
    "editor_in_chief": ("艾達・王", "艾達"),
    "news_intelligence": ("雪拉・瑪絲", "雪拉"),
}


def upgrade() -> None:
    bind = op.get_bind()
    for role, (name, description) in STAFF.items():
        bind.execute(
            sa.text(
                "UPDATE agents SET display_name = :name, description = :description "
                f"WHERE role = :role AND status = 'active' AND company_id IN ({NEWSROOM_COMPANIES})"
            ),
            {"role": role, "name": name, "description": description},
        )


def downgrade() -> None:
    bind = op.get_bind()
    for role, (long, short) in OLD.items():
        bind.execute(
            sa.text(
                "UPDATE agents SET display_name = replace(display_name, :short, :long), "
                "description = replace(description, :short, :long) "
                f"WHERE role = :role AND status = 'active' AND company_id IN ({NEWSROOM_COMPANIES})"
            ),
            {"role": role, "short": short, "long": long},
        )
