"""D-252: an article nobody approved goes to the CEO within 8 hours, on her shift; she is told
how old it is against its section's shelf life, and only past its hard limit is that a reason.

The 6 articles she turned down before D-252 were all turned down as more than a day old; the
cases below are theirs.
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from autora.db.models import SystemSetting
from autora.domains.newsroom.agents.ceo_approval import SYSTEM_PROMPT, freshness
from autora.domains.newsroom.policy import (
    CEO_AFTER_HOURS_KEY,
    SHELF_LIFE_KEY,
    ceo_after_hours,
    shelf_life_hours,
)
from autora.domains.newsroom.workflow import handover_at, office_shifts
from autora.runtime.actor import Actor
from autora.runtime.shifts import Shifts

OFFICE = Shifts.parse("mon-fri 15:00-21:00; sat-sun 18:00-21:00", "mon-sun", "Asia/Taipei")
EIGHT = timedelta(hours=8)


def taipei(day: int, hour: int, minute: int = 0) -> datetime:
    """2026-10-``day`` in Taipei (the 12th is a Monday, the 17th a Saturday)."""
    return datetime(2026, 10, day, hour, minute, tzinfo=ZoneInfo("Asia/Taipei"))


def test_asked_on_a_weekday_shift_it_is_hers_before_the_shift_ends():
    assert handover_at(taipei(12, 15, 11), EIGHT, OFFICE) == taipei(12, 20, 30)


def test_asked_on_a_weekend_shift_too():
    assert handover_at(taipei(17, 18, 11), EIGHT, OFFICE) == taipei(17, 20, 30)


def test_a_shorter_wait_is_kept():
    assert handover_at(taipei(12, 15, 0), timedelta(hours=2), OFFICE) == taipei(12, 17, 0)


def test_asked_in_the_last_half_hour_or_off_shift_it_is_hers_early_next_shift():
    assert handover_at(taipei(12, 20, 45), EIGHT, OFFICE) == taipei(13, 15, 30)
    assert handover_at(taipei(12, 23, 0), EIGHT, OFFICE) == taipei(13, 15, 30)
    assert handover_at(taipei(16, 22, 0), EIGHT, OFFICE) == taipei(17, 18, 30)  # Friday night


def test_without_shifts_it_is_the_clock_alone():
    assert handover_at(taipei(12, 23, 0), EIGHT, None) == taipei(13, 7, 0)


def test_the_shift_a_moment_is_in_ends():
    assert OFFICE.shift_end(taipei(12, 15, 11)) == taipei(12, 21, 0)
    assert OFFICE.shift_end(taipei(17, 18, 0)) == taipei(17, 21, 0)
    assert OFFICE.shift_end(taipei(12, 21, 0)) is None
    assert OFFICE.shift_end(taipei(17, 15, 0)) is None  # Saturday afternoon: off


def test_the_wait_is_the_company_s_within_bounds():
    assert ceo_after_hours({}) == 8
    assert ceo_after_hours({CEO_AFTER_HOURS_KEY: 4}) == 4
    for bad in (0, -1, 25, "8", True, None):
        assert ceo_after_hours({CEO_AFTER_HOURS_KEY: bad}) == 8


def test_shelf_lives_by_section_and_the_company_s_own():
    assert [shelf_life_hours({}, s) for s in ("crypto", "tw", "ai", "holdings", None)] == [
        48, 72, 120, 336, 72,
    ]  # fmt: skip
    mine = {SHELF_LIFE_KEY: {"crypto": 24, "tw": "x"}}
    assert (shelf_life_hours(mine, "crypto"), shelf_life_hours(mine, "tw")) == (24, 72)


def _said(hours: float, section: str, shelf: int) -> str:
    return "\n".join(freshness(asked=timedelta(hours=hours), section=section, shelf_life=shelf))


def test_what_the_ceo_is_told_of_the_six_she_turned_down():
    # 智邦 27h and 奇鋐 51h (tw), XRP 24h and CFTC 24h (crypto): within shelf life
    for hours, section, shelf in ((27, "tw", 72), (51, "tw", 72), (24, "crypto", 48)):
        said = _said(hours, section, shelf)
        assert "Within its shelf life: timeliness is not a reason to reject." in said
    # 為升 179h (tw): past its shelf life, within the hard limit of 216h — published
    assert "within the hard limit" in _said(179, "tw", 72)
    # SEC Cboe 149h (crypto): past the hard limit of 144h — still turned down, the one of six
    assert "Past its hard limit: stale" in _said(149, "crypto", 48)
    said = _said(30, "tw", 72)
    assert "Section: tw; shelf life 72 hours, hard limit 216 hours." in said
    assert "30 hours old when the desk asked for approval" in said


def test_the_ceo_publishes_unless_she_can_name_why_not():
    assert "If you are unsure, approve." in SYSTEM_PROMPT
    assert "If you are unsure, reject" not in SYSTEM_PROMPT
    assert "more than a day old is stale" not in SYSTEM_PROMPT


async def test_the_shifts_are_the_back_office_s_when_set(db_session):
    assert await office_shifts(db_session) is None  # the tests' environment: always at work
    db_session.add(
        SystemSetting(
            key="worker.shifts",
            value="mon-fri 15:00-21:00",
            updated_by=Actor.human("operator").as_json(),
        )
    )
    await db_session.flush()
    shifts = await office_shifts(db_session)
    assert shifts is not None and shifts.shift_end(taipei(12, 16)) == taipei(12, 21)
