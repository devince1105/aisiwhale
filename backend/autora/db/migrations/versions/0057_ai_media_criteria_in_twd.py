"""AI Media's kill criteria in NT$, and a mission that says no revenue is expected yet (D-117)

The criterion was written as ``cost_per_published_article > 3.0`` when the base currency was the
US dollar. D-023 made the base NT$, so the same 3.0 came to mean NT$3 — less than an article
costs — and on 2026-09-27 the CEO paused the newsroom for it (and for "zero revenue", on a site
that is free on purpose). Only the criterion still reading 3.0 is changed.

Revision ID: 0057
Revises: 0056
Create Date: 2026-09-29
"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0057"
down_revision: str | None = "0056"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MISSION = "Bilingual finance reporting that says where every fact came from. The site is free while it builds its readers (D-035): no revenue is expected yet, so judge it on what it publishes, how good that is, who reads it and what it costs — not on sales."
OLD_MISSION = "Bilingual reporting that says where every fact came from."
KILL_CRITERIA = {
    "evaluate_after_cycles": 7,
    "auto_pause_if": {
        "metric": "cost_per_published_article",
        "op": ">",
        "value": 100.0,
        "unit": "TWD per published article",
    },
}
OLD_KILL_CRITERIA = {
    "evaluate_after_cycles": 7,
    "auto_pause_if": {"metric": "cost_per_published_article", "op": ">", "value": 3.0},
}
STILL_OLD = "key = 'ai_media' AND (kill_criteria -> 'auto_pause_if' ->> 'value')::numeric = 3.0"


def upgrade() -> None:
    op.get_bind().execute(
        sa.text(
            "UPDATE business_units SET kill_criteria = CAST(:criteria AS jsonb), mission = :mission "
            f"WHERE {STILL_OLD}"
        ),
        {"criteria": json.dumps(KILL_CRITERIA), "mission": MISSION},
    )


def downgrade() -> None:
    op.get_bind().execute(
        sa.text(
            "UPDATE business_units SET kill_criteria = CAST(:criteria AS jsonb), mission = :mission "
            "WHERE key = 'ai_media' AND mission = :new"
        ),
        {"criteria": json.dumps(OLD_KILL_CRITERIA), "mission": OLD_MISSION, "new": MISSION},
    )
