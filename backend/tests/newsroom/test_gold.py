"""D-070: the 黃金 tab — spot gold from Tiingo's forex prices, a few asks a day, and what it is in
New Taiwan dollars a gram at the day's reference rate."""

from datetime import UTC, date, datetime, timedelta

import httpx

from autora.domains.newsroom.fx_rates import FxBoard
from autora.domains.newsroom.gold import GRAMS_PER_OUNCE, TIINGO_GOLD, GoldBoard, bars_from
from tests.newsroom.test_fx_rates import answer

ROWS = [
    {"date": "2026-09-24T00:00:00.000Z", "open": 4700, "high": 4760, "low": 4690, "close": 4750},
    {"date": "2026-09-25T00:00:00.000Z", "open": 4750, "high": 4800, "low": 4700, "close": 4800},
    {"date": "2026-09-25T00:00:00.000Z", "open": 4750, "high": 4810, "low": 4700, "close": 4805},
    {"date": "2026-09-23T00:00:00.000Z", "open": 4650, "high": 4710, "low": 4640, "close": 4700},
    {"date": "not a day", "open": 1, "high": 1, "low": 1, "close": 1},
    {"date": "2026-09-22T00:00:00.000Z", "open": 1, "high": 1, "low": 1, "close": 0},
]


def test_one_bar_a_day_oldest_first_without_volume():
    bars = bars_from(ROWS)
    assert [(b.d, b.c) for b in bars] == [
        (date(2026, 9, 23), 4700),
        (date(2026, 9, 24), 4750),
        (date(2026, 9, 25), 4805),  # the day said twice: the last one
    ]
    assert {b.v for b in bars} == {0}


def test_the_sunday_evening_is_monday_s_and_an_untraded_weekend_is_left_out():
    rows = [
        {
            "date": "2026-09-18T00:00:00.000Z",
            "open": 4346,
            "high": 4399,
            "low": 4334,
            "close": 4380,
        },
        {
            "date": "2026-09-20T00:00:00.000Z",
            "open": 4380,
            "high": 4382,
            "low": 4369,
            "close": 4372,
        },
        {
            "date": "2026-09-21T00:00:00.000Z",
            "open": 4372,
            "high": 4383,
            "low": 4322,
            "close": 4368,
        },
        {
            "date": "2026-09-25T00:00:00.000Z",
            "open": 4265,
            "high": 4315,
            "low": 4254,
            "close": 4284,
        },
        {
            "date": "2026-09-27T00:00:00.000Z",
            "open": 4284,
            "high": 4284,
            "low": 4284,
            "close": 4284,
        },
    ]
    bars = bars_from(rows)
    assert [b.d.isoformat() for b in bars] == ["2026-09-18", "2026-09-21", "2026-09-25"]
    monday = bars[1]
    assert (monday.o, monday.h, monday.l, monday.c) == (4380, 4383, 4322, 4368)


async def test_the_price_its_change_and_a_gram_in_new_taiwan_dollars():
    now = [datetime(2026, 9, 27, 3, tzinfo=UTC)]
    asked: list[tuple[str, dict]] = []

    async def get(url: str, params: dict) -> list[dict]:
        asked.append((url, params))
        return ROWS

    async def rates(url: str) -> dict:
        return answer()

    board = GoldBoard(get, FxBoard(rates, clock=lambda: now[0]), clock=lambda: now[0])
    gold = await board.gold("zh-TW")
    assert gold is not None and (gold.as_of, gold.usd_per_oz) == (date(2026, 9, 25), 4805)
    assert round(gold.change, 2) == 55 and round(gold.change_pct, 3) == round(55 / 4750 * 100, 3)
    usd = 1 / 0.031486
    assert round(gold.twd_per_gram, 2) == round(4805 * usd / GRAMS_PER_OUNCE, 2)
    assert asked[0][0] == TIINGO_GOLD and asked[0][1]["resampleFreq"] == "1day"
    assert asked[0][1]["startDate"] <= "2021-09-27"  # about five years
    await board.gold("en")
    assert len(asked) == 1, "one ask serves every reader for a few hours"

    async def down(url: str, params: dict) -> list[dict]:
        raise httpx.ConnectError("down")

    board.get = down
    now[0] += timedelta(hours=4)
    assert (await board.gold("zh-TW")).usd_per_oz == 4805, "the last good answer stands"


async def test_without_a_rate_the_gram_is_left_out_and_offline_there_is_nothing():
    async def get(url: str, params: dict) -> list[dict]:
        return ROWS

    gold = await GoldBoard(get, FxBoard(None)).gold("zh-TW")
    assert gold is not None and gold.twd_per_gram is None
    assert await GoldBoard(None, FxBoard(None)).gold("zh-TW") is None
