"""What the runtime can do, for forms that must not offer the impossible (T-517 follow-up).

``GET /api/roles``: the roles that have a behavior, so hiring an agent that would never pick up a
task is not offered in the first place.
``GET /api/office-hours``: when the AI staff work (D-193), so a quiet office out of hours is not
taken for a broken one.
``GET /api/office-hours/call``: for the worker alone, with WORKER_CALL_TOKEN — when a person last
changed something in the back office (D-205). Off its shifts, it comes in when that is new.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from autora.app import build_behaviors
from autora.infra.settings import Settings
from autora.runtime.shifts import Shifts
from autora_api.deps import OFFICE_CALL, Operator, settings_dep

SettingsDep = Annotated[Settings, Depends(settings_dep)]
_worker_bearer = HTTPBearer(auto_error=False)

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
    called_at: datetime | None = None
    """When a person last changed something here (D-205): off its shifts the worker comes in for
    it within a minute or so, while the day's and the month's overtime last."""


@router.get("/office-hours")
async def office_hours(_: Operator, settings: SettingsDep) -> OfficeHours:
    """The worker's shifts, read from the settings the worker shares: no database query."""
    shifts = Shifts.parse(settings.worker_shifts, settings.worker_days, settings.worker_timezone)
    now = datetime.now(UTC)
    on_duty = shifts is None or shifts.on_duty(now)
    return OfficeHours(
        shifts=[g.strip() for g in settings.worker_shifts.split(";") if g.strip()],
        days=settings.worker_days,
        timezone=settings.worker_timezone,
        on_duty=on_duty,
        next_start=None if on_duty or shifts is None else shifts.next_start(now),
        called_at=OFFICE_CALL.at,
    )


@router.get("/office-hours/call", include_in_schema=False)
async def office_call(
    settings: SettingsDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_worker_bearer)],
) -> dict[str, datetime | None]:
    """The worker's question, off its shifts (D-205): has a person done something? Answered from
    memory — the database sleeps through it — and only to WORKER_CALL_TOKEN."""
    expected = settings.worker_call_token.get_secret_value()
    if (
        not expected
        or credentials is None
        or not secrets.compare_digest(credentials.credentials, expected)
    ):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "the worker's token only")
    return {"called_at": OFFICE_CALL.at}
