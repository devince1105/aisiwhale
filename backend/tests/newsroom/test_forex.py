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
    TIINGO_CRYPTO,
    TIINGO_FX,
    TiingoFx,
    bars_from,
    crossed,
    crypto_bars,
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


BTC = [
    {
        "ticker": "btcusd",
        "priceData": [
            {
                "date": "2026-09-26T00:00:00+00:00",
                "open": 84000,
                "high": 85500,
                "low": 83900,
                "close": 85000,
                "volume": 1900.5,
            },
            {
                "date": "2026-09-27T00:00:00+00:00",
                "open": 85000,
                "high": 85100,
                "low": 84200,
                "close": 84729.72,
                "volume": 1864.4,
            },
        ],
    }
]


def tiingo(asked: list[str], *, down: bool = False):
    async def get(url: str, params: dict) -> list[dict]:
        asked.append(url)
        if down:
            raise httpx.ConnectError("down")
        if url == TIINGO_CRYPTO:
            return BTC if params["tickers"] == "btcusd" else []
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


def test_a_coin_trades_every_day_so_its_weekend_stays():
    bars = crypto_bars(BTC)
    assert [(b.d.isoformat(), b.c) for b in bars] == [
        ("2026-09-26", 85000),
        ("2026-09-27", 84729.72),
    ]
    assert (bars[0].h, bars[0].l, bars[0].v) == (85500, 83900, 0)
    assert crypto_bars([]) == [] and crypto_bars([{"ticker": "x", "priceData": None}]) == []


async def test_bitcoin_and_the_taiwan_index_have_charts_with_their_open_high_and_low():
    asked: list[str] = []
    figures = Figures(TiingoFx(tiingo(asked)), FredHistory(None))
    btc = await figures.figure("btc")
    assert btc is not None and (btc.value, btc.source, btc.close_only) == (
        84729.72,
        "Tiingo",
        False,
    )
    await figures.figure("btc")
    assert asked == [TIINGO_CRYPTO], "a coin, too, once every few hours"
    assert await figures.figure("eth") is None  # no Ether in the fixture
    assert await figures.figure("taiex") is None  # without the database: nothing to read
    yen = await figures.figure("jpytwd")
    assert yen.close_only and not (await figures.figure("usdtwd")).close_only


def test_the_figures_a_story_names_by_its_section():
    """D-079: a crypto, gold, futures or FX story links the watchlist figures it names — only
    its own kind, so a stock story's 美元 or an FX story's 黃金 links nothing."""
    from autora.domains.newsroom.figures import figures_named

    keys = lambda text, section: [k for k, _, _ in figures_named(text, section)]  # noqa: E731
    assert keys("比特幣 ETF 資金流入，以太幣走弱", "crypto") == ["btc", "eth"]
    assert keys("金價創高", "gold") == ["xau"]
    assert keys("國際油價下跌，黃金走高", "commodities") == ["wti", "us:USO", "xau"]  # D-081
    assert keys("CBOT 玉米期貨下跌", "commodities") == ["maize", "us:CORN"]  # D-080
    assert keys("新台幣兌美元收 31.716，日圓、人民幣走弱，歐元持平", "fx") == [
        "usdtwd",
        "jpytwd",
        "eurtwd",
        "cnytwd",
    ]  # in Bank of Taiwan's order
    assert keys("The yen won back its losses", "fx") == ["jpytwd"]  # "won" is not the won
    assert keys("黃金與美元", "fx") == ["usdtwd"] and keys("美元走強", "tw") == []
    # a stock story's index: the Nasdaq and the yield in US news, the TAIEX in Taiwan's
    assert keys("那指跌1.13%，美債殖利率上升", "us") == ["nasdaq", "us10y"]
    assert keys("Nasdaq fell as Treasury yields rose", "us") == ["nasdaq", "us10y"]
    assert keys("加權指數收高", "tw") == ["taiex"]
    assert keys("台積電殖利率約1.5%", "tw") == []  # a dividend yield is not the Treasury's
    assert keys("比特幣", None) == []


async def test_grains_the_imf_s_month_and_the_fund_that_holds_the_futures():
    """D-080: corn, soybeans and wheat — the IMF's world price a month at a time (FRED), and
    each grain's Teucrium fund (a US ETF of CBOT futures) for the days between."""
    from autora.domains.newsroom.figures import GRAINS, figures_named

    asked: list[str] = []

    async def fred(series: str) -> list[dict]:
        asked.append(series)
        return [
            {"date": "2026-06-01", "value": "195.78"},
            {"date": "2026-07-01", "value": "213.19"},
        ]

    corn = await Figures(TiingoFx(None), FredHistory(fred)).figure("maize")
    assert corn is not None and (corn.interval, corn.source, corn.value) == (
        "month",
        "IMF (FRED)",
        213.19,
    )
    assert asked == [GRAINS["maize"][0]]
    assert {fund for *_, fund in GRAINS.values()} == {"CORN", "SOYB", "WEAT"}
    keys = lambda text: [k for k, _, _ in figures_named(text, "commodities")]  # noqa: E731
    assert keys("CBOT玉米期貨跌0.47%，大豆、小麥同步走低") == [
        "maize",
        "us:CORN",
        "soybeans",
        "us:SOYB",
        "wheat",
        "us:WEAT",
    ]
    assert keys("玉米") == ["maize", "us:CORN"] and figures_named("玉米", "tw") == []
