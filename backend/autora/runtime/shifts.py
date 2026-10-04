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
class Roster:
    """Shifts kept in one time zone: weekday (0 is Monday) -> its windows, earliest first."""

    zone: ZoneInfo
    by_day: dict[int, tuple[tuple[time, time], ...]]

    def on_duty(self, now: datetime) -> bool:
        local = now.astimezone(self.zone)
        windows = self.by_day.get(local.weekday(), ())
        return any(begins <= local.time() < ends for begins, ends in windows)

    def next_start(self, now: datetime) -> datetime | None:
        local = now.astimezone(self.zone)
        for ahead in range(8):
            day = (local + timedelta(days=ahead)).date()
            for begins, _ in self.by_day.get(day.weekday(), ()):
                start = datetime.combine(day, begins, tzinfo=self.zone)
                if start > local:
                    return start
        return None


@dataclass(frozen=True)
class Shifts:
    rosters: tuple[Roster, ...]

    @classmethod
    def parse(
        cls, spec: str, days: str = "mon-sun", timezone: str = "Asia/Taipei"
    ) -> Shifts | None:
        """None for an empty ``spec``: no shifts, always at work.

        ``spec`` is shifts for ``days`` (``07:00-11:00,19:00-23:00``), or groups separated by
        ``;``, each ``[days] shifts [time zone]`` (D-194, D-195): ``mon-fri 08:00-09:00,
        13:30-14:30; mon-fri 08:30-09:30,16:00-17:00 America/New_York; sat-sun 09:00-10:00``.
        A group without a zone is in ``timezone``: the New York market's hours stay its hours
        through daylight saving."""
        if not spec.strip():
            return None
        by_zone: dict[str, dict[int, list[tuple[time, time]]]] = {}
        for group in (g.strip() for g in spec.split(";") if g.strip()):
            words = group.split()
            zone = words.pop() if words and "/" in words[-1] else timezone
            group_days = _days(words.pop(0)) if words and words[0][:1].isalpha() else _days(days)
            windows = _windows(" ".join(words).replace(" ", ""))
            if not windows:
                raise ShiftsError(f"no shifts in {group!r}")
            try:
                ZoneInfo(zone)
            except Exception as exc:  # noqa: BLE001 - an unknown zone, however it is reported
                raise ShiftsError(f"not a time zone: {zone!r}") from exc
            for day in group_days:
                by_zone.setdefault(zone, {}).setdefault(day, []).extend(windows)
        return cls(
            tuple(
                Roster(ZoneInfo(zone), {d: tuple(sorted(w)) for d, w in days_.items()})
                for zone, days_ in by_zone.items()
            )
        )

    def on_duty(self, now: datetime) -> bool:
        return any(roster.on_duty(now) for roster in self.rosters)

    def next_start(self, now: datetime) -> datetime:
        """The next clock-in after ``now`` (in ``now``'s zone)."""
        starts = [s for s in (r.next_start(now) for r in self.rosters) if s is not None]
        if not starts:
            raise ShiftsError("no shift in the coming week")
        return min(starts).astimezone(now.tzinfo)

    def hours_a_week(self) -> float:
        """How long the office is open in a week."""
        return sum(
            (datetime.combine(datetime.min, e) - datetime.combine(datetime.min, b)).seconds / 3600
            for roster in self.rosters
            for windows in roster.by_day.values()
            for b, e in windows
        )
