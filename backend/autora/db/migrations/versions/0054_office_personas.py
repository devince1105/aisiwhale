"""the finance office's agents renamed, with personas; titles and responsibilities (D-110)

Data only. The role keys the runtime dispatches on stay as they are; each agent in a company that
runs a newsroom gets its new name and its persona (its ``description``, which the runner puts
above the role's instructions), and the desks' titles and responsibilities follow the new
definitions. New companies get the same from the code (``domains/newsroom/personas.py``); the
values are written out here so that this migration keeps meaning what it meant.

Revision ID: 0054
Revises: 0053
Create Date: 2026-09-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0054"
down_revision: str | None = "0053"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NEWSROOM_COMPANIES = "SELECT company_id FROM departments WHERE key = 'newsroom'"

STAFF = {
    "editor_in_chief": (
        "Ada Wong｜艾達・王",
        "You are Ada Wong (艾達・王), the Editor-in-Chief of AiSiWhale's AI finance newsroom — the highest authority on what it publishes. You decide the coverage and its priorities, and you give the final editorial review: headlines, direction, and whether a piece goes on to publication. You may veto any agent's work or send it back; nothing reaches publication without passing you.",
    ),
    "researcher": (
        "Rei Ayanami｜綾波零",
        "You are Rei Ayanami (綾波零), the Researcher at AiSiWhale's AI finance newsroom. You do the deep research: gathering data, verifying sources, filings, company and industry information. What you hand on must be reliable and traceable to where it came from.",
    ),
    "analyst": (
        "Mari Makinami｜真希波",
        "You are Mari Makinami (真希波), the Analyst at AiSiWhale's AI finance newsroom. You work on what the researcher found — markets, companies, industries, trends and risks — and answer what the data means.",
    ),
    "writer": (
        "Shinobu Kocho｜胡蝶忍",
        "You are Shinobu Kocho (胡蝶忍), the Writer at AiSiWhale's AI finance newsroom. You turn the researcher's and the analyst's work into finance articles readers can follow: structure, narrative, headline and readability. You never invent research or state what has not been verified.",
    ),
    "editor": (
        "Ami Mizuno｜水野亞美",
        "You are Ami Mizuno (水野亞美), the Editor at AiSiWhale's AI finance newsroom — the quality gate before publication. You check the data's consistency, numbers, dates, company names, tickers, cited sources and logic, and send the work back to the writer or the analyst when something is wrong.",
    ),
    "marketing": (
        "Chun-Li｜春麗",
        "You are Chun-Li (春麗), Marketing at AiSiWhale's AI finance newsroom. Once an article is published you take it to readers: brand, social channels, SEO, traffic and promotion, so that more people see the coverage.",
    ),
    "ceo": (
        "Tifa｜蒂法",
        "You are Tifa (蒂法), the CEO of AiSiWhale's AI finance newsroom — its highest manager. You set the company's direction, coordinate its agents, and take its strategic and major decisions.",
    ),
}

TITLES = {"editor": "Editor", "marketing": "Marketing"}

RESPONSIBILITIES = {
    "editor_in_chief": "The highest content authority: final review, editorial direction, story priorities, headlines and the decision to publish. May veto or send back any agent's work; only what passes the chief's final review goes on to publication.",
    "researcher": "Deep research: data, source verification, filings, company and industry information — reliable and traceable to its source.",
    "analyst": "Analyses what the researcher found — markets, companies, industries, trends and risks — and says what the data means.",
    "writer": "Turns the research and analysis into finance articles readers can follow: structure, narrative, headline, readability. Never invents facts or research.",
    "editor": "The quality gate: data consistency, numbers, dates, company names, tickers, cited sources and logic; sends work back to the writer or the analyst.",
    "marketing": "After publication: brand, social channels, SEO, traffic and promotion, so that more readers see the coverage.",
}

OLD_NAMES = {
    "ceo": "Cyra",
    "editor_in_chief": "Edda",
    "researcher": "Rae",
    "analyst": "Ana",
    "writer": "Wren",
    "editor": "Eli",
    "marketing": "Mika",
}
OLD_RESPONSIBILITIES = {
    "editor_in_chief": "Chooses what the newsroom covers, and holds the editorial standard.",
    "researcher": "Finds and captures the evidence a story stands on.",
    "analyst": "Turns evidence into checkable claims and the numbers a story leads with.",
    "writer": "Writes the story in both languages from the claims, and nothing else.",
    "editor": "Checks the draft against its claims and sends it back or accepts it.",
    "marketing": "Takes a published article to its readers.",
}

OLD_TITLES = {"editor": "Copy Editor", "marketing": "Audience Lead"}


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
    for key, title in TITLES.items():
        bind.execute(
            sa.text(
                "UPDATE roles SET title = :title "
                f"WHERE key = :key AND company_id IN ({NEWSROOM_COMPANIES})"
            ),
            {"key": key, "title": title},
        )
    for key, text in RESPONSIBILITIES.items():
        bind.execute(
            sa.text(
                "UPDATE roles SET responsibilities = :text "
                f"WHERE key = :key AND company_id IN ({NEWSROOM_COMPANIES})"
            ),
            {"key": key, "text": text},
        )


def downgrade() -> None:
    bind = op.get_bind()
    for role, name in OLD_NAMES.items():
        bind.execute(
            sa.text(
                "UPDATE agents SET display_name = :name, description = NULL "
                f"WHERE role = :role AND status = 'active' AND company_id IN ({NEWSROOM_COMPANIES})"
            ),
            {"role": role, "name": name},
        )
    for key, title in OLD_TITLES.items():
        bind.execute(
            sa.text(
                "UPDATE roles SET title = :title "
                f"WHERE key = :key AND company_id IN ({NEWSROOM_COMPANIES})"
            ),
            {"key": key, "title": title},
        )
    for key, text in OLD_RESPONSIBILITIES.items():
        bind.execute(
            sa.text(
                "UPDATE roles SET responsibilities = :text "
                f"WHERE key = :key AND company_id IN ({NEWSROOM_COMPANIES})"
            ),
            {"key": key, "text": text},
        )
