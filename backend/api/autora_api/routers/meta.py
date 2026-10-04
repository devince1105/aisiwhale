"""What the runtime can do, for forms that must not offer the impossible (T-517 follow-up).

``GET /api/roles``: the roles that have a behavior, so hiring an agent that would never pick up a
task is not offered in the first place.
``GET /api/office-hours``: when the AI staff work (D-193), so a quiet office out of hours is not
taken for a broken one.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from autora.app import build_behaviors
from autora.infra.settings import Settings
from autora.runtime.shifts import Shifts
from autora_api.deps import Operator, settings_dep

SettingsDep = Annotated[Settings, Depends(settings_dep)]

router = APIRouter(prefix="/api", tags=["meta"])


class Roles(BaseModel):
    roles: list[str]


@router.get("/roles")
async def list_roles(_: Operator) -> Roles:
    return Roles(roles=build_behaviors().roles())


class OfficeHours(BaseModel):
    """When the AI staff work (D-193). ``shifts`` empty: always at work."""

    shifts: list[str]
    days: str
    timezone: str
    on_duty: bool
    next_start: datetime | None
    """The next clock-in, when off duty."""


@router.get("/office-hours")
async def office_hours(_: Operator, settings: SettingsDep) -> OfficeHours:
    """The worker's shifts, read from the settings the worker shares: no database query."""
    shifts = Shifts.parse(settings.worker_shifts, settings.worker_days, settings.worker_timezone)
    now = datetime.now(UTC)
    on_duty = shifts is None or shifts.on_duty(now)
    return OfficeHours(
        shifts=[s.strip() for s in settings.worker_shifts.split(",") if s.strip()],
        days=settings.worker_days,
        timezone=settings.worker_timezone,
        on_duty=on_duty,
        next_start=None if on_duty or shifts is None else shifts.next_start(now),
    )
