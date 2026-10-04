"""Office hours (D-193): when the worker works, and when it leaves the database alone.

Neon bills compute for every hour the database runs, and it only suspends after five minutes
without a query. A worker that polls around the clock — for work, for due schedules — keeps it
up all day. With shifts set, the worker works within them and, outside them, finishes what it
has started and then waits for the next shift without a single query: the database can sleep,
waking briefly for a reader of the public site.

``WORKER_SHIFTS`` is a list of ``HH:MM-HH:MM`` windows (``07:00-11:00,19:00-23:00``) on
``WORKER_DAYS`` (``mon-fri``, or ``mon,wed,fri``), in ``WORKER_TIMEZONE`` — or groups of days with
shifts of their own (D-194): ``mon-fri 07:00-09:00,14:00-16:00; sat-sun 09:00-10:00``.
Empty: always at work, as before — the tests and a developer's machine. Schedules that came due
overnight fire once at the next clock-in (the scheduler collapses missed runs); approvals due
overnight are decided then.
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


def _windows(spec: str) -> list[tuple[time, time]]:
    windows = []
    for part in (p.strip() for p in spec.split(",") if p.strip()):
        start, _, end = part.partition("-")
        if not end:
            raise ShiftsError(f"not a shift: {part!r} (HH:MM-HH:MM)")
        begins, ends = _clock(start), _clock(end)
        if ends <= begins:
            raise ShiftsError(f"a shift ends after it begins, the same day: {part!r}")
        windows.append((begins, ends))
    return windows


@dataclass(frozen=True)
class Shifts:
    by_day: dict[int, tuple[tuple[time, time], ...]]
    """Weekday (0 is Monday) -> its shifts, earliest first; a day not here is a day off."""
    zone: ZoneInfo

    @classmethod
    def parse(
        cls, spec: str, days: str = "mon-sun", timezone: str = "Asia/Taipei"
    ) -> Shifts | None:
        """None for an empty ``spec``: no shifts, always at work.

        ``spec`` is shifts for ``days`` (``07:00-11:00,19:00-23:00``), or groups of days with
        their own shifts, separated by ``;`` (D-194): ``mon-fri 07:00-09:00,14:00-16:00;
        sat-sun 09:00-10:00``."""
        if not spec.strip():
            return None
        by_day: dict[int, list[tuple[time, time]]] = {}
        for group in (g.strip() for g in spec.split(";") if g.strip()):
            head, _, rest = group.partition(" ")
            if head[:1].isalpha():
                group_days, windows = _days(head), _windows(rest)
            else:
                group_days, windows = _days(days), _windows(group)
            if not windows:
                raise ShiftsError(f"no shifts for {head!r}")
            for day in group_days:
                by_day.setdefault(day, []).extend(windows)
        return cls({d: tuple(sorted(w)) for d, w in by_day.items()}, ZoneInfo(timezone))

    def on_duty(self, now: datetime) -> bool:
        local = now.astimezone(self.zone)
        return any(
            begins <= local.time() < ends for begins, ends in self.by_day.get(local.weekday(), ())
        )

    def next_start(self, now: datetime) -> datetime:
        """The next clock-in after ``now`` (in ``now``'s zone)."""
        local = now.astimezone(self.zone)
        for ahead in range(8):
            day = (local + timedelta(days=ahead)).date()
            for begins, _ in self.by_day.get(day.weekday(), ()):
                start = datetime.combine(day, begins, tzinfo=self.zone)
                if start > local:
                    return start.astimezone(now.tzinfo)
        raise ShiftsError("no shift in the coming week")

    def hours_a_week(self) -> float:
        """How long the office is open in a week."""
        return sum(
            (datetime.combine(datetime.min, e) - datetime.combine(datetime.min, b)).seconds / 3600
            for windows in self.by_day.values()
            for b, e in windows
        )
