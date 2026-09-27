"""D-070–D-072: spot gold and currencies against the New Taiwan dollar from Tiingo's forex
prices, one shared cache — each pair asked for once every few hours for everything that shows it
— and the Nasdaq, the 10-year yield and oil from FRED, for the watchlist's charts."""

from datetime import UTC, date, datetime, timedelta

import httpx
import pytest

from autora.domains.newsroom.figures import Figures, FredHistory, closes, currency_of
from autora.domains.newsroom.forex import (
    CHARTED,
    CURRENCIES,
    TIINGO_FX,
    TiingoFx,
    bars_from,
    crossed,
)
from autora.domains.newsroom.gold import GRAMS_PER_OUNCE, GoldBoard


def row(day: str, o: float, h: float, low: float, c: float) -> dict:
    return {"date": f"{day}T00:00:00.000Z", "open": o, "high": h, "low": low, "close": c}


GOLD = [
    row("2026-09-24", 4288, 4303, 4244, 4265.09),
    row("2026-09-25", 4265, 4315, 4254, 4284.91),
    row("2026-09-27", 4284.91, 4284.91, 4284.91, 4284.91),  # Sunday, before the market opens
]
USDTWD = [row("2026-09-24", 31.7, 31.8, 31.6, 31.78), row("2026-09-25", 31.78, 31.8, 31.7, 31.72)]
USDJPY = [row("2026-09-24", 157, 158, 156, 157.5), row("2026-09-25", 157.5, 158, 157, 157.3)]
PAIRS = {
    "xauusd": GOLD,
    "usdtwd": USDTWD,
    "usdjpy": USDJPY,
    "eurusd": [row("2026-09-25", 1.1, 1.2, 1.0, 1.14)],
}


def test_one_bar_a_trading_day_a_sunday_evening_is_monday_s():
    bars = bars_from(
        [
            row("2026-09-18", 4346, 4399, 4334, 4380),
            row("2026-09-20", 4380, 4382, 4369, 4372),  # Sunday evening (UTC): Monday in Taipei
            row("2026-09-21", 4372, 4383, 4322, 4368),
            row("2026-09-25", 4265, 4315, 4254, 4284),
            row("2026-09-25", 4265, 4316, 4254, 4285),  # the day said twice: the last one
            row("2026-09-27", 4285, 4285, 4285, 4285),  # an untraded Sunday: left out
            {"date": "not a day", "open": 1, "high": 1, "low": 1, "close": 1},
        ]
    )
    assert [b.d.isoformat() for b in bars] == ["2026-09-18", "2026-09-21", "2026-09-25"]
    assert (bars[1].o, bars[1].h, bars[1].l, bars[1].c) == (4380, 4383, 4322, 4368)
    assert bars[2].c == 4285 and {b.v for b in bars} == {0}


def test_a_currency_in_new_taiwan_dollars_from_two_pairs_closes_only():
    twd = bars_from(USDTWD)
    yen = crossed(twd, bars_from(USDJPY), per_usd=True)
    assert [round(b.c, 5) for b in yen] == [round(31.78 / 157.5, 5), round(31.72 / 157.3, 5)]
    assert all(b.o == b.h == b.l == b.c for b in yen)
    euro = crossed(twd, bars_from(PAIRS["eurusd"]), per_usd=False)
    assert [(b.d, round(b.c, 4)) for b in euro] == [(date(2026, 9, 25), round(31.72 * 1.14, 4))]


def test_the_charted_currencies_are_bank_of_taiwan_s():
    assert set(CHARTED) <= {code for code, _, _ in CURRENCIES}
    assert {"USD", "JPY", "CNY", "EUR", "HKD"} <= set(CHARTED)
    assert "THB" not in CHARTED  # Tiingo has no baht
    assert (currency_of("jpytwd"), currency_of("JPYTWD"), currency_of("thbtwd")) == (
        "JPY",
        "JPY",
        None,
    )
    assert currency_of("usd") is None and currency_of("nasdaq") is None


def tiingo(asked: list[str], *, down: bool = False):
    async def get(url: str, params: dict) -> list[dict]:
        asked.append(url)
        if down:
            raise httpx.ConnectError("down")
        pair = url.split("/fx/")[1].split("/")[0]
        return PAIRS[pair]

    return get


async def test_each_pair_asked_for_once_every_few_hours_whoever_wants_it():
    now = [datetime(2026, 9, 27, 3, tzinfo=UTC)]
    asked: list[str] = []
    forex = TiingoFx(tiingo(asked), clock=lambda: now[0])
    gold = await GoldBoard(forex).gold("zh-TW")
    assert gold is not None and (gold.as_of, gold.usd_per_oz) == (date(2026, 9, 25), 4284.91)
    assert round(gold.change, 2) == 19.82
    assert round(gold.twd_per_gram, 2) == round(4284.91 * 31.72 / GRAMS_PER_OUNCE, 2)
    await forex.twd_bars("JPY")
    await forex.twd_bars("USD")
    await GoldBoard(forex).gold("en")
    assert sorted(asked) == sorted(TIINGO_FX.format(pair=p) for p in ("xauusd", "usdtwd", "usdjpy"))
    # a failure keeps the last good answer, and is not asked again for a while
    forex.get = tiingo(asked, down=True)
    now[0] += timedelta(hours=4)
    assert (await forex.bars("xauusd"))[-1].c == 4284.91
    await forex.bars("xauusd")
    assert len(asked) == 4


async def test_offline_there_is_nothing_and_nobody_is_asked():
    forex = TiingoFx(None)
    assert await forex.bars("usdtwd") == [] and await GoldBoard(forex).gold("zh-TW") is None


FRED_ROWS = [
    {"date": "2026-09-23", "value": "4.12"},
    {"date": "2026-09-24", "value": "."},
    {"date": "2026-09-25", "value": "4.09"},
]


async def test_figures_a_currency_from_tiingo_and_the_rest_from_fred():
    assert [(b.d, b.c) for b in closes(FRED_ROWS)] == [
        (date(2026, 9, 23), 4.12),
        (date(2026, 9, 25), 4.09),
    ]
    asked: list[str] = []

    async def fred(series: str) -> list[dict]:
        asked.append(series)
        return FRED_ROWS

    figures = Figures(TiingoFx(tiingo([])), FredHistory(fred))
    yield_ = await figures.figure("us10y")
    assert yield_ is not None and yield_.source == "FRED" and yield_.change_pct is None
    assert round(yield_.change, 2) == -0.03  # points, not a percentage
    await figures.figure("us10y")
    assert asked == ["DGS10"], "each series once every six hours"
    yen = await figures.figure("jpytwd")
    assert (
        yen is not None
        and yen.source == "Tiingo"
        and round(yen.value, 5) == round(31.72 / 157.3, 5)
    )
    assert yen.change_pct == pytest.approx((31.72 / 157.3 - 31.78 / 157.5) / (31.78 / 157.5) * 100)
    assert await figures.figure("taiex") is None and await figures.figure("thbtwd") is None
    offline = Figures(TiingoFx(None), FredHistory(None))
    assert await offline.figure("wti") is None and await offline.figure("usdtwd") is None
