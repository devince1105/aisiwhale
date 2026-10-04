"""The office's style, one per company, set in the back office (D-178).

The 3D office has five styles (D-011). They used to be a choice each browser remembered for
itself; now the company has one, chosen in the back office's office settings, and the public
site's AI 編輯部 shows the site's company in it — a reader has no setting to change it.
Kept as a company policy (``office.theme``): a presentation choice, not a rule an agent reads.
"""

from __future__ import annotations

import uuid
from typing import Literal, get_args

from sqlalchemy.ext.asyncio import AsyncSession

from autora.db.repositories.companies import get_policies, upsert_policy
from autora.runtime.actor import Actor

OFFICE_THEME_KEY = "office.theme"

OfficeTheme = Literal["muji", "wabisabi", "industrial", "google", "cyber"]
"""The styles the web app draws (``office3d/palette.ts`` ``ThemeId``)."""
OFFICE_THEMES: tuple[str, ...] = get_args(OfficeTheme)
DEFAULT_OFFICE_THEME: OfficeTheme = "muji"


async def office_theme(session: AsyncSession, company_id: uuid.UUID) -> OfficeTheme:
    """The company's style; the default until one is chosen (or if one stored is unknown)."""
    stored = (await get_policies(session, company_id)).get(OFFICE_THEME_KEY)
    return stored if stored in OFFICE_THEMES else DEFAULT_OFFICE_THEME  # type: ignore[return-value]


async def set_office_theme(
    session: AsyncSession, company_id: uuid.UUID, theme: OfficeTheme, *, actor: Actor
) -> None:
    if theme not in OFFICE_THEMES:
        raise ValueError(f"unknown office theme {theme!r}")
    await upsert_policy(session, company_id, OFFICE_THEME_KEY, theme, updated_by=actor.as_json())
