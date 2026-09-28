"""D-088: 財經行事曆 — FRED's release dates and Finnhub's earnings dates, twice a day."""

from datetime import UTC, date, datetime, timedelta

from autora.domains.newsroom.economic_calendar import (
    FINNHUB_EARNINGS,
    FRED_DATES,
    EconomicCalendar,
)

NAMES = {"TSM": ("台積電 ADR", "TSMC ADR"), "NVDA": ("輝達", "Nvidia"), "MU": ("美光", "Micron")}
NOW = datetime(2026, 9, 28, 2, tzinfo=UTC)  # 10:00 in Taipei


def services(asked: list[str], *, down: bool = False):
    async def fred(url: str, params: dict) -> dict:
        assert url == FRED_DATES
        asked.append(f"fred:{params['release_id']}")
        if down:
            raise RuntimeError("HTTP 500")
        dates = {10: ["2026-10-14"], 50: ["2026-10-02"], 53: ["2026-09-27", "2026-09-30"]}
        return {"release_dates": [{"date": d} for d in dates.get(params["release_id"], [])]}

    async def finnhub(url: str, params: dict) -> dict:
        assert url == FINNHUB_EARNINGS
        asked.append(f"finnhub:{params['symbol']}")
        rows = {
            "TSM": [{"date": "2026-10-14", "hour": "amc", "quarter": 3, "year": 2026}],
            "MU": [{"date": "2026-09-30", "hour": "bmo", "quarter": 4, "year": 2026}],
        }
        return {"earningsCalendar": rows.get(params["symbol"], [])}

    return fred, finnhub


async def test_the_coming_releases_and_earnings_soonest_first():
    asked: list[str] = []
    fred, finnhub = services(asked)
    calendar = EconomicCalendar(fred, finnhub, NAMES, clock=lambda: NOW)
    events = await calendar.events("zh-TW")
    assert [(e.day.isoformat(), e.name, e.detail, e.key) for e in events] == [
        ("2026-09-30", "美國 GDP", None, "release:53"),
        ("2026-09-30", "美光 財報", "2026Q4 盤前", "us:MU"),
        ("2026-10-02", "美國就業報告（非農就業）", None, "release:50"),
        ("2026-10-14", "美國消費者物價指數（CPI）", None, "release:10"),
        ("2026-10-14", "台積電 財報", "2026Q3 盤後", "us:TSM"),
        ("2026-10-28", "聯準會利率決議（FOMC）", "美東 14:00", "fomc"),
    ]  # 9/27 is past; a day's releases before its earnings; TSMC under its own name
    english = await calendar.events("en", limit=2)
    assert [e.name for e in english] == ["US GDP", "Micron earnings", "Fed rate decision (FOMC)"]
    assert english[1].detail == "2026Q4 before the open"
    assert len([a for a in asked if a.startswith("fred")]) == 5, "once for every reader"


async def test_the_last_answer_stands_and_offline_there_is_none():
    now = [NOW]
    asked: list[str] = []
    fred, finnhub = services(asked)
    calendar = EconomicCalendar(fred, finnhub, NAMES, clock=lambda: now[0])
    assert len(await calendar.events("zh-TW")) == 6
    calendar.fred, calendar.finnhub = services(asked, down=True)
    now[0] += timedelta(days=3)  # 10/1 in Taipei: asked again, and the service is down
    assert len(await calendar.events("zh-TW")) == 4  # the last answer, less the days now past
    assert await EconomicCalendar(None, None, NAMES).events("zh-TW") == []
    # without Finnhub's key: the releases alone
    only_fred = EconomicCalendar(services([])[0], None, NAMES, clock=lambda: NOW)
    assert {e.kind for e in await only_fred.events("zh-TW")} == {"macro"}
    assert date(2026, 9, 30) in {e.day for e in await only_fred.events("zh-TW")}


async def test_the_fed_s_decisions_from_its_own_calendar():
    """D-089: the FOMC's decision days as the Fed publishes them; a meeting with projections
    says so."""
    from autora.domains.newsroom.economic_calendar import FOMC_DECISIONS

    december = datetime(2026, 11, 20, 2, tzinfo=UTC)
    calendar = EconomicCalendar(*services([]), NAMES, clock=lambda: december)
    [fed] = [e for e in await calendar.events("en") if e.key == "fomc"]
    assert (fed.day, fed.name, fed.detail) == (
        date(2026, 12, 9),
        "Fed rate decision (FOMC)",
        "2 p.m. ET, with projections",
    )
    assert len(FOMC_DECISIONS) == 16 and all(
        d.startswith(("2026", "2027")) for d, _ in FOMC_DECISIONS
    )
    assert sum(p for _, p in FOMC_DECISIONS) == 8  # four meetings a year publish projections


async def test_the_next_fed_decision_always_shows():
    """D-089: however many releases and earnings come first, the next decision is listed."""
    calendar = EconomicCalendar(*services([]), NAMES, clock=lambda: NOW)
    two = await calendar.events("zh-TW", limit=2)
    assert [e.key for e in two] == ["release:53", "us:MU", "fomc"]
    # seven weeks between meetings (7/29 to 9/16): still found from the day after the first
    summer = EconomicCalendar(
        *services([]), NAMES, clock=lambda: datetime(2026, 7, 30, 2, tzinfo=UTC)
    )
    assert [e.day for e in await summer.events("zh-TW") if e.key == "fomc"] == [date(2026, 9, 16)]
