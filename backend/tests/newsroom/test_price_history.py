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


async def test_a_first_fill_takes_five_years_and_a_later_one_only_the_months_since(db_session):
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
    assert written == 2 and len(asked) == 60 and asked[0] == "20211001" and asked[-1] == "20260901"

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
