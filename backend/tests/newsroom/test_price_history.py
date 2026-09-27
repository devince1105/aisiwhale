"""D-059: Taiwan's daily prices from TWSE, stored for the stock pages' charts."""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import delete, select

from autora.domains.newsroom import price_history
from autora.domains.newsroom.models import PriceBar

FIELDS = [
    "日期",
    "成交股數",
    "成交金額",
    "開盤價",
    "最高價",
    "最低價",
    "收盤價",
    "漲跌價差",
    "成交筆數",
    "註記",
]
SEPTEMBER = {
    "stat": "OK",
    "fields": FIELDS,
    "data": [  # as TWSE answered for 2330, 2026-09
        row.split("|")
        for row in (
            "115/09/01|31,855,287|77,463,413,685|2,395.00|2,440.00|2,390.00|2,440.00|+35.00|65,271|",
            "115/09/02|25,151,394|60,261,105,308|2,415.00|2,420.00|2,385.00|2,385.00|-55.00|198,779|",
            "115/09/03|0|0|--|--|--|--| 0.00|0|",
        )
    ],
}  # fmt: skip


def test_a_month_reads_as_bars_and_a_day_without_trade_is_left_out():
    bars = price_history.parse_twse_month(SEPTEMBER)
    assert [b.day for b in bars] == [date(2026, 9, 1), date(2026, 9, 2)]
    first = bars[0]
    assert (first.open, first.high, first.low, first.close) == (
        Decimal("2395.00"), Decimal("2440.00"), Decimal("2390.00"), Decimal("2440.00")
    )  # fmt: skip
    assert first.volume == 31_855_287


def test_a_month_with_no_data_is_empty_and_a_refusal_is_an_error():
    assert price_history.parse_twse_month({"stat": "很抱歉，沒有符合條件的資料!"}) == []
    with pytest.raises(price_history.PriceError):
        price_history.parse_twse_month({"stat": "查詢日期大於今日，請重新查詢!"})


def test_months_run_from_first_to_last():
    months = price_history.months_between(date(2025, 11, 20), date(2026, 2, 3))
    assert months == [date(2025, 11, 1), date(2025, 12, 1), date(2026, 1, 1), date(2026, 2, 1)]


async def test_a_first_fill_takes_the_last_year_and_a_later_one_only_the_months_since(db_session):
    """D-061: a stock just asked for gets its last year first; the years before follow."""
    await db_session.execute(delete(PriceBar).where(PriceBar.symbol == "TEST"))
    asked: list[str] = []

    async def get(url, params):
        asked.append(params["date"])
        return (
            SEPTEMBER
            if params["date"] == "20260901"
            else {"stat": "OK", "fields": FIELDS, "data": []}
        )

    written = await price_history.refresh_tw(
        db_session, get, today=date(2026, 9, 27), symbols=("TEST",), pause=0
    )
    # twelve months to September, then back from August until a month has no trades (here: at
    # once, as the fake has only September)
    assert written == 2 and asked[:12] == [f"2025{m:02d}01" for m in (10, 11, 12)] + [
        f"2026{m:02d}01" for m in range(1, 10)
    ]
    assert asked[12:] == ["20260801"]

    asked.clear()
    await price_history.refresh_tw(
        db_session, get, today=date(2026, 9, 28), symbols=("TEST",), pause=0
    )
    # from the last stored day's month on (stored again, not twice); and one month before the
    # first — empty: the stock was not trading, so nothing older is asked for
    assert asked == ["20260901", "20260801"]
    days = (await db_session.scalars(select(PriceBar.day).where(PriceBar.symbol == "TEST"))).all()
    assert sorted(days) == [date(2026, 9, 1), date(2026, 9, 2)]
    await db_session.execute(delete(PriceBar).where(PriceBar.symbol == "TEST"))


async def test_one_month_that_fails_does_not_stop_the_rest(db_session):
    await db_session.execute(delete(PriceBar).where(PriceBar.symbol == "TEST"))

    async def get(url, params):
        if params["date"] == "20260801":
            raise TimeoutError("TWSE did not answer")
        return (
            SEPTEMBER
            if params["date"] == "20260901"
            else {"stat": "OK", "fields": FIELDS, "data": []}
        )

    written = await price_history.refresh_tw(
        db_session, get, today=date(2026, 9, 27), symbols=("TEST",), pause=0
    )
    assert written == 2
    await db_session.execute(delete(PriceBar).where(PriceBar.symbol == "TEST"))


TIINGO_ROW = {  # as Tiingo answered for NVDA, 2026-09-21
    "date": "2026-09-21T00:00:00.000Z", "close": 227.38, "high": 228.5, "low": 221.56,
    "open": 222.935, "volume": 109806067, "adjClose": 227.38, "adjHigh": 228.5, "adjLow": 221.56,
    "adjOpen": 222.935, "adjVolume": 109806067, "divCash": 0.0, "splitFactor": 1.0,
}  # fmt: skip


def test_tiingo_rows_read_as_adjusted_bars():
    [bar] = price_history.parse_tiingo([TIINGO_ROW, {"date": "2026-09-22"}])  # half a row: left out
    assert bar.day == date(2026, 9, 21) and bar.close == Decimal("227.38")
    assert bar.open == Decimal("222.935") and bar.volume == 109_806_067


async def test_us_stocks_ask_for_two_years_every_time_and_one_failure_does_not_stop_the_rest(
    db_session,
):
    await db_session.execute(delete(PriceBar).where(PriceBar.symbol.in_(("TESTA", "TESTB"))))
    asked = []

    async def get(url, params):
        asked.append((url.rsplit("/", 2)[-2], params["startDate"]))
        if "TESTA" in url:
            raise TimeoutError("no answer")
        return [TIINGO_ROW]

    written = await price_history.refresh_us(
        db_session, get, today=date(2026, 9, 27), symbols=("TESTA", "TESTB"), pause=0
    )
    assert written == 1
    assert asked == [("TESTA", "2021-10-01"), ("TESTB", "2021-10-01")]
    await db_session.execute(delete(PriceBar).where(PriceBar.symbol.in_(("TESTA", "TESTB"))))


def test_an_error_says_nothing_a_key_could_hide_in():
    import httpx

    request = httpx.Request("GET", "https://api.tiingo.com/x?token=secret")
    error = httpx.HTTPStatusError("401", request=request, response=httpx.Response(401))
    assert price_history._describe(error) == "HTTPStatusError (HTTP 401)"


async def test_a_shorter_history_is_extended_back_to_five_years(db_session):
    """Two years stored (as before), five wanted: the months before the first, newest first,
    until a month had no trades."""
    await db_session.execute(delete(PriceBar).where(PriceBar.symbol == "TEST"))

    def month(year, number):
        return {"stat": "OK", "fields": FIELDS, "data": [
            f"{year - 1911}/{number:02d}/02|1,000|1|10.00|11.00|9.00|10.50|0|1|".split("|")
        ]}  # fmt: skip

    listed_since = (2024, 3)

    async def get(url, params):
        year, number = int(params["date"][:4]), int(params["date"][4:6])
        return (
            month(year, number)
            if (year, number) >= listed_since
            else {"stat": "OK", "fields": FIELDS, "data": []}
        )

    await price_history._store(
        db_session, "tw", "TEST", price_history.parse_twse_month(month(2024, 10)), source="TWSE"
    )
    asked = []

    async def counting(url, params):
        asked.append(params["date"][:6])
        return await get(url, params)

    await price_history.refresh_tw(
        db_session, counting, today=date(2024, 10, 20), symbols=("TEST",), pause=0
    )
    assert asked == ["202410", "202409", "202408", "202407", "202406", "202405", "202404",
                     "202403", "202402"]  # fmt: skip
    days = (await db_session.scalars(select(PriceBar.day).where(PriceBar.symbol == "TEST"))).all()
    assert min(days) == date(2024, 3, 2) and len(days) == 8
    await db_session.execute(delete(PriceBar).where(PriceBar.symbol == "TEST"))


def _iex(day: str, time: str, close: float) -> dict:
    return {"date": f"{day}T{time}:00.000Z", "open": close, "high": close, "low": close,
            "close": close, "volume": 100.0}  # fmt: skip


def test_iex_bars_keep_the_last_five_trading_days():
    days = ["2026-09-17", "2026-09-18", "2026-09-21", "2026-09-22", "2026-09-23", "2026-09-24"]
    rows = [_iex(d, "13:30", 1.0) for d in days] + [_iex("2026-09-24", "13:45", 2.0), {"date": "x"}]
    bars = price_history.parse_iex(rows)
    assert sorted({b.t.date().isoformat() for b in bars}) == days[1:]
    assert bars[-1].c == 2.0 and bars[-1].t.minute == 45


async def test_intraday_asks_tiingo_at_most_every_ten_minutes_and_keeps_the_last_answer():
    from datetime import UTC, datetime, timedelta

    now = [datetime(2026, 9, 25, 15, 0, tzinfo=UTC)]
    asked = []

    async def get(url, params):
        asked.append(params["resampleFreq"])
        if len(asked) == 2:
            raise TimeoutError("no answer")
        return [_iex("2026-09-25", "13:30", 1.0)]

    cache = price_history.IntradayCache(get, clock=lambda: now[0])
    first = await cache.bars("NVDA")
    assert first.source == "Tiingo IEX" and len(first.bars) == 1
    now[0] += timedelta(minutes=5)
    assert await cache.bars("NVDA") == first and asked == ["15min"]  # kept
    now[0] += timedelta(minutes=6)
    assert await cache.bars("NVDA") == first and len(asked) == 2  # asked; failed; the last kept
    assert (await price_history.IntradayCache(None).bars("NVDA")).bars == []  # no key


def _bars(*closes: float) -> list:
    return [
        price_history.PublicBar(d=date(2025, 6, 10 + i), o=c, h=c, l=c, c=c, v=1000)
        for i, c in enumerate(closes)
    ]


def test_a_split_is_read_from_the_prices_and_the_bars_before_it_scaled():
    """0050, 2025-06-18: 188.65 then 47.57, a 1-for-4 split TWSE's figures leave unadjusted."""
    assert price_history.split_factors(_bars(186.0, 188.65, 47.57, 48.0)) == [4, 4, 1, 1]
    # a reverse split, 1 share for 2
    assert price_history.split_factors(_bars(10.0, 20.2, 20.5)) == [0.5, 1, 1]


def test_ordinary_days_and_odd_jumps_are_left_alone():
    assert price_history.split_factors(_bars(100, 110, 99, 108.9)) == [1, 1, 1, 1]  # limit moves
    # a capital reduction (a ratio that is not whole) is not taken for a split
    assert price_history.split_factors(_bars(30.0, 43.5)) == [1, 1]


async def test_a_taiwan_history_is_served_split_adjusted(db_session):
    await db_session.execute(delete(PriceBar).where(PriceBar.symbol == "TEST"))
    bars = [
        price_history.Bar(date(2025, 6, 17), Decimal("188"), Decimal("189"), Decimal("187"),
                          Decimal("188.65"), 1000),
        price_history.Bar(date(2025, 6, 18), Decimal("47.5"), Decimal("48"), Decimal("47"),
                          Decimal("47.57"), 4000),
    ]  # fmt: skip
    await price_history._store(db_session, "tw", "TEST", bars, source="TWSE")
    served = (await price_history.history(db_session, "tw", "TEST")).bars
    assert served[0].c == round(188.65 / 4, 4) and served[0].v == 4000
    assert served[1].c == 47.57
    stored = await db_session.scalar(
        select(PriceBar.close).where(PriceBar.symbol == "TEST").order_by(PriceBar.day)
    )
    assert stored == Decimal("188.6500")  # kept as the exchange published it
    await db_session.execute(delete(PriceBar).where(PriceBar.symbol == "TEST"))


TPEX_SEPTEMBER = {
    "stat": "ok",
    "tables": [{
        "fields": ["日 期", "成交張數", "成交仟元", "開盤", "最高", "最低", "收盤", "漲跌", "筆數"],
        "data": [  # as TPEx answered for 6488, 2026-09
            "115/09/01|12,770|12,430,205|908.00|998.00|908.00|994.00|82.00|31,831".split("|"),
            "115/09/02|7,323|7,068,011|976.00|982.00|951.00|967.00|-27.00|22,814".split("|"),
        ],
    }],
}  # fmt: skip


def test_a_tpex_month_reads_as_bars_with_volume_in_shares():
    bars = price_history.parse_tpex_month(TPEX_SEPTEMBER)
    assert [b.day for b in bars] == [date(2026, 9, 1), date(2026, 9, 2)]
    assert bars[0].close == Decimal("994.00") and bars[0].volume == 12_770_000  # 張 x 1000


async def test_a_tpex_stock_is_asked_of_tpex_without_extending_on_a_first_fill(db_session):
    await db_session.execute(delete(PriceBar).where(PriceBar.symbol == "6488"))
    asked = []

    async def get(url, params):
        asked.append(url)
        return (
            TPEX_SEPTEMBER
            if params.get("date") == "2026/09/01"
            else {
                "stat": "ok",
                "tables": [{"fields": TPEX_SEPTEMBER["tables"][0]["fields"], "data": []}],
            }
        )

    written = await price_history.refresh_tw(
        db_session, get, today=date(2026, 9, 27), symbols=("6488",),
        exchanges={"6488": "TPEx"}, pause=0, extend=False,
    )  # fmt: skip
    assert written == 2 and len(asked) == 12 and set(asked) == {price_history.TPEX_DAY}
    source = await db_session.scalar(select(PriceBar.source).where(PriceBar.symbol == "6488"))
    assert source == "TPEx"
    await db_session.execute(delete(PriceBar).where(PriceBar.symbol == "6488"))


async def test_a_quote_off_the_strip_is_its_last_two_closes(db_session):
    await db_session.execute(delete(PriceBar).where(PriceBar.symbol == "TEST"))
    assert await price_history.bar_quote(db_session, "us", "TEST") is None
    later = {**TIINGO_ROW, "date": "2026-09-22T00:00:00.000Z", "adjClose": 230.0}
    bars = price_history.parse_tiingo([TIINGO_ROW, later])
    await price_history._store(db_session, "us", "TEST", bars, source="Tiingo")
    quote = await price_history.bar_quote(db_session, "us", "TEST")
    assert quote.value == 230.0 and quote.previous_close == 227.38 and quote.basis == "close"
    assert quote.change_pct == round((230 / 227.38 - 1) * 100, 2) and quote.key == "us:TEST"
    await db_session.execute(delete(PriceBar).where(PriceBar.symbol == "TEST"))


async def test_a_us_stock_asks_for_the_days_since_and_everything_again_after_a_split(db_session):
    await db_session.execute(delete(PriceBar).where(PriceBar.symbol == "TEST"))
    await price_history._store(
        db_session, "us", "TEST", price_history.parse_tiingo([TIINGO_ROW]), source="Tiingo"
    )
    asked = []

    async def get(url, params):
        asked.append(params["startDate"])
        split = len(asked) == 1
        return [
            {**TIINGO_ROW, "date": "2026-09-24T00:00:00.000Z", "splitFactor": 4.0 if split else 1.0}
        ]

    await price_history.refresh_us(
        db_session, get, today=date(2026, 9, 27), symbols=("TEST",), pause=0
    )
    assert asked == ["2026-09-14", "2021-10-01"]  # a week before the last bar; then five years
    await db_session.execute(delete(PriceBar).where(PriceBar.symbol == "TEST"))


INDEX_SEPTEMBER = {  # as TWSE answered for 2026-09
    "stat": "OK",
    "fields": ["日期", "開盤指數", "最高指數", "最低指數", "收盤指數"],
    "data": [
        ["115/09/01", "46,177.11", "46,948.72", "46,081.11", "46,948.72"],
        ["115/09/02", "46,901.32", "46,946.60", "46,164.72", "46,164.72"],
    ],
}


def test_the_index_month_reads_as_bars_without_volume():
    bars = price_history.parse_index_month(INDEX_SEPTEMBER)
    assert [(b.day, b.close, b.volume) for b in bars] == [
        (date(2026, 9, 1), Decimal("46948.72"), 0),
        (date(2026, 9, 2), Decimal("46164.72"), 0),
    ]
    assert price_history.parse_index_month({"stat": "很抱歉，沒有符合條件的資料!"}) == []


async def test_the_taiwan_index_is_one_more_taiwan_symbol_and_served_unadjusted(db_session):
    """D-073: the TAIEX's days, asked of TWSE's index history a month at a time, stored with the
    stocks'; a day's fall of more than a stock's 10% limit is not read as a split."""
    await db_session.execute(delete(PriceBar).where(PriceBar.symbol == price_history.INDEX))
    asked = []

    async def get(url, params):
        asked.append((url, params))
        if params["date"] == "20260901":
            crash = {
                **INDEX_SEPTEMBER,
                "data": [
                    *INDEX_SEPTEMBER["data"],
                    ["115/09/03", "46,164.72", "46,164.72", "40,000.00", "40,000.00"],
                ],
            }
            return crash
        return {"stat": "很抱歉，沒有符合條件的資料!"}

    written = await price_history.refresh_tw(
        db_session, get, today=date(2026, 9, 27), symbols=(price_history.INDEX,), pause=0,
        extend=False,
    )  # fmt: skip
    assert written == 3
    assert {url for url, _ in asked} == {price_history.TWSE_INDEX_DAY}
    assert all("stockNo" not in params for _, params in asked)
    served = await price_history.history(db_session, "tw", price_history.INDEX)
    assert [b.c for b in served.bars] == [46948.72, 46164.72, 40000.0]  # not "split"
    await db_session.execute(delete(PriceBar).where(PriceBar.symbol == price_history.INDEX))


async def test_the_scheduled_refresh_asks_for_the_index_first():
    keeper = price_history.PricesKeeper(price_history.no_prices)

    class Session:
        async def scalars(self, *_):
            return []

        async def execute(self, *_):
            class Rows:
                def all(self):
                    return []

            return Rows()

    symbols, _ = await keeper._tw(Session())
    assert symbols[0] == price_history.INDEX
