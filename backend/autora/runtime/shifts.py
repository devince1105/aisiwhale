"""Office hours (D-193): when the worker works, and when it leaves the database alone.

Neon bills compute for every hour the database runs, and it only suspends after five minutes
without a query. A worker that polls around the clock — for work, for due schedules — keeps it
up all day. With shifts set, the worker works within them and, outside them, finishes what it
has started and then waits for the next shift without a single query: the database can sleep,
waking briefly for a reader of the public site.

``WORKER_SHIFTS`` is a list of ``HH:MM-HH:MM`` windows (``07:00-11:00,19:00-23:00``) on
``WORKER_DAYS`` (``mon-fri``, or ``mon,wed,fri``), in ``WORKER_TIMEZONE``. Empty: always at work,
as before — the tests and a developer's machine. Schedules that came due overnight fire once at
the next clock-in (the scheduler collapses missed runs); approvals due overnight are decided then.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


class ShiftsError(ValueError):
    pass


def _clock(text: str) -> time:
    try:
        hours, minutes = text.strip().split(":")
        return time(int(hours), int(minutes))
    except ValueError as exc:
        raise ShiftsError(f"not a time of day: {text!r} (HH:MM)") from exc


def _days(spec: str) -> frozenset[int]:
    out: set[int] = set()
    for part in (p.strip().lower() for p in spec.split(",") if p.strip()):
        if "-" in part:
            first, last = (DAYS.index(d.strip()) for d in part.split("-"))
            out.update(
                range(first, last + 1) if first <= last else [*range(first, 7), *range(0, last + 1)]
            )
        elif part in DAYS:
            out.add(DAYS.index(part))
        else:
            raise ShiftsError(f"not a day: {part!r} ({', '.join(DAYS)})")
    if not out:
        raise ShiftsError("no working days")
    return frozenset(out)


@dataclass(frozen=True)
class Shifts:
    windows: tuple[tuple[time, time], ...]
    days: frozenset[int]
    zone: ZoneInfo

    @classmethod
    def parse(
        cls, spec: str, days: str = "mon-sun", timezone: str = "Asia/Taipei"
    ) -> Shifts | None:
        """None for an empty ``spec``: no shifts, always at work."""
        if not spec.strip():
            return None
        windows = []
        for part in (p for p in spec.split(",") if p.strip()):
            start, _, end = part.partition("-")
            if not end:
                raise ShiftsError(f"not a shift: {part!r} (HH:MM-HH:MM)")
            begins, ends = _clock(start), _clock(end)
            if ends <= begins:
                raise ShiftsError(f"a shift ends after it begins, the same day: {part!r}")
            windows.append((begins, ends))
        return cls(tuple(sorted(windows)), _days(days), ZoneInfo(timezone))

    def on_duty(self, now: datetime) -> bool:
        local = now.astimezone(self.zone)
        if local.weekday() not in self.days:
            return False
        return any(begins <= local.time() < ends for begins, ends in self.windows)

    def next_start(self, now: datetime) -> datetime:
        """The next clock-in after ``now`` (in ``now``'s zone)."""
        local = now.astimezone(self.zone)
        for ahead in range(8):
            day = (local + timedelta(days=ahead)).date()
            if day.weekday() not in self.days:
                continue
            for begins, _ in self.windows:
                start = datetime.combine(day, begins, tzinfo=self.zone)
                if start > local:
                    return start.astimezone(now.tzinfo)
        raise ShiftsError("no shift in the coming week")
