"""Settings the back office changes while everything runs (AD-11, D-234).

A few of the environment's values are a person's to tune, not a deploy's: when the AI staff
work (D-205's shifts), how much overtime a day and a month allow, how many 聯絡我們 messages a
day. Each is defined here — its type, its bounds, what it means — with the environment's value
as its default; one set in the back office (``system_settings``) wins until it is reset.
Secrets and wiring stay in the environment.

Nobody keeps a database awake for them (D-205: off its shifts the worker asks nothing):

- the API holds the values in memory, read once at its start (the deploy's migrations just woke
  the database) and changed with every save (``autora_api.live``);
- the worker reads them when the database is awake anyway: every maintenance pass of a shift,
  and when a call is about to begin (``LiveOvertime.left``) — so a raised overtime limit is seen
  by the very call it lets in. ``LiveShifts`` and ``LiveOvertime`` stand where ``Shifts`` and
  ``Overtime`` stood: the worker itself is unchanged.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from autora.db.models import SystemSetting
from autora.infra.settings import Settings
from autora.runtime.oncall import Overtime
from autora.runtime.shifts import Shifts, ShiftsError

log = logging.getLogger(__name__)


class SettingError(ValueError):
    pass


@dataclass(frozen=True)
class SettingDef:
    key: str
    kind: Literal["shifts", "hours", "count"]
    label: str
    help: str
    env: str
    """The environment's field: the default."""
    minimum: float | None = None
    maximum: float | None = None


DEFINITIONS: dict[str, SettingDef] = {
    d.key: d
    for d in (
        SettingDef(
            "worker.shifts",
            "shifts",
            "AI 員工的上班時段",
            "例：mon-fri 15:00-21:00; sat-sun 18:00-21:00。"
            "下班時只有你在後台動作才會臨時上班（D-205）。"
            "清空表示全天上班，模型費用會跟著增加。",
            "worker_shifts",
        ),
        SettingDef(
            "worker.overtime_day_hours",
            "hours",
            "每日加班上限（小時）",
            "臨時上班一天最多幾小時；勞基法：連同正常工時一天不超過 12 小時（D-205）。",
            "worker_overtime_day_hours",
            0,
            4,
        ),
        SettingDef(
            "worker.overtime_month_hours",
            "hours",
            "每月加班上限（小時）",
            "臨時上班一個月最多幾小時；勞基法 §32 上限 46 小時（D-205）。",
            "worker_overtime_month_hours",
            0,
            46,
        ),
        SettingDef(
            "contact.daily_cap",
            "count",
            "「聯絡我們」每日上限（則）",
            "網站聯絡表單一天最多轉寄幾則，超過的當天不再寄（防灌爆信箱）。",
            "contact_daily_cap",
            0,
            1000,
        ),
    )
}


def default(settings: Settings, key: str) -> Any:
    return getattr(settings, DEFINITIONS[key].env)


def normalize(settings: Settings, key: str, value: Any) -> Any:
    """The value as stored, or SettingError saying why it cannot be."""
    definition = DEFINITIONS.get(key)
    if definition is None:
        raise SettingError(f"no setting {key!r}")
    if definition.kind == "shifts":
        if not isinstance(value, str):
            raise SettingError("shifts are text")
        spec = value.strip()
        try:
            parsed = Shifts.parse(spec, settings.worker_days, settings.worker_timezone)
            if parsed is not None:
                parsed.next_start(datetime.now(parsed.rosters[0].zone))
        except ShiftsError as exc:
            raise SettingError(str(exc)) from exc
        return spec
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise SettingError("a number")
    number = int(value) if definition.kind == "count" else float(value)
    if definition.kind == "count" and number != value:
        raise SettingError("a whole number")
    if definition.minimum is not None and number < definition.minimum:
        raise SettingError(f"at least {definition.minimum:g}")
    if definition.maximum is not None and number > definition.maximum:
        raise SettingError(f"at most {definition.maximum:g}")
    return number


async def stored(session: AsyncSession) -> dict[str, Any]:
    """What the back office set, by key (a key no longer defined is left out)."""
    rows = await session.execute(select(SystemSetting.key, SystemSetting.value))
    return {key: value for key, value in rows if key in DEFINITIONS}


def effective(settings: Settings, overrides: dict[str, Any]) -> dict[str, Any]:
    return {key: overrides.get(key, default(settings, key)) for key in DEFINITIONS}


# --- the worker's side ------------------------------------------------------------------------


class LiveShifts:
    """``Shifts`` whose roster can be replaced while the worker runs. None inside: always at work,
    as a worker with no shifts is."""

    def __init__(self, shifts: Shifts | None) -> None:
        self.shifts = shifts

    def on_duty(self, now: datetime) -> bool:
        return self.shifts is None or self.shifts.on_duty(now)

    def next_start(self, now: datetime) -> datetime:
        if self.shifts is None:
            return now
        return self.shifts.next_start(now)


@dataclass
class LiveOvertime(Overtime):
    """``Overtime`` that reads the limits set in the back office before it says what is left: a
    call is the moment the database is awake for a person's action, and a limit just raised is
    what lets that call in."""

    reload: Callable[[], Awaitable[None]] | None = field(default=None)

    async def left(self, now: datetime) -> timedelta:
        if self.reload is not None:
            await self.reload()
        return await super().left(now)


def apply(
    settings: Settings, values: dict[str, Any], shifts: LiveShifts, overtime: Overtime
) -> None:
    """Put the effective values where the worker reads them."""
    spec = values["worker.shifts"]
    try:
        shifts.shifts = Shifts.parse(spec, settings.worker_days, settings.worker_timezone)
    except ShiftsError:
        log.exception("live settings: shifts %r do not parse; the ones before stay", spec)
    overtime.day_limit = timedelta(hours=float(values["worker.overtime_day_hours"]))
    overtime.month_limit = timedelta(hours=float(values["worker.overtime_month_hours"]))


def worker_reloader(
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
    shifts: LiveShifts,
    overtime: Overtime,
) -> tuple[Callable[[], Awaitable[None]], Callable[[AsyncSession], Awaitable[None]]]:
    """``(reload, maintenance_job)``: a reload in a session of its own (for a call about to
    begin), and the same as a maintenance job (every pass of a shift). A failure keeps the
    values the worker has."""

    async def from_session(session: AsyncSession) -> None:
        apply(settings, effective(settings, await stored(session)), shifts, overtime)

    async def reload() -> None:
        try:
            async with session_factory() as session:
                await from_session(session)
        except Exception:  # noqa: BLE001 - the worker works on with what it had
            log.warning("live settings: cannot read them; the ones before stay", exc_info=True)

    return reload, from_session
