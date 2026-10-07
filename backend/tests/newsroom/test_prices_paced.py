"""D-244: the scheduled price refresh asks a few stocks a run. It asked every one in a run,
Tiingo's 75 seconds apart — some 120 US stocks, two and a half hours in which no other schedule
ran (10/07: poll_sources last at 15:00, begun again after every deploy). Now at most
``TW_PER_RUN`` requests of Taiwan's exchanges and ``US_PER_RUN`` of Tiingo's, each stock read
once a day, the longest unread first, remembered in ``price_fetches``."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import delete, select

from autora.domains.newsroom import price_history
from autora.domains.newsroom.market_strip import TW_STOCKS, US_STOCKS
from autora.domains.newsroom.models import PriceFetch
from autora.domains.newsroom.price_history import (
    INDEX,
    TIINGO_DAILY,
    TWSE_INDEX_DAY,
    Bar,
    PricesKeeper,
    _store,
    asked,
    due,
)

CLOCK_IN = datetime(2026, 10, 7, 7, 0, tzinfo=UTC)  # 15:00 in Taipei, a Wednesday
TRACKED_US = tuple(f"T{n:03d}" for n in range(107))  # with the strip's 13: 120, as on 10/07
TRACKED_TW = ("2603", "3008")
TIINGO_ROW = {
    "date": "2026-10-06T00:00:00.000Z", "adjOpen": 10.0, "adjHigh": 11.0, "adjLow": 9.0,
    "adjClose": 10.5, "adjVolume": 1000, "splitFactor": 1.0,
}  # fmt: skip


@pytest.fixture(autouse=True)
async def nothing_asked_yet(db_session):
    """Other tests' workers ran the refresh with the database committed (offline: every symbol
    read, none asked of an exchange); in here, inside the test's own transaction, none was."""
    await db_session.execute(delete(PriceFetch).where(PriceFetch.market.in_(("tw", "us"))))


@pytest.fixture
def slept(monkeypatch):
    """Every pause the run takes, in seconds, none of them waited for."""
    pauses: list[float] = []

    async def sleep(seconds):
        pauses.append(seconds)

    monkeypatch.setattr(price_history.asyncio, "sleep", sleep)
    return pauses


@pytest.fixture
def tracked(monkeypatch):
    async def symbols(session, market, **_):
        return list(TRACKED_US if market == "us" else TRACKED_TW)

    async def exchange_of(session, symbols):
        return {}

    monkeypatch.setattr(price_history.securities, "tracked", symbols)
    monkeypatch.setattr(price_history.securities, "exchange_of", exchange_of)


async def five_years_stored(session):
    """Every Taiwan symbol's history already back five years and up to yesterday: a day's
    refresh is one request each (this month), as in production."""
    bars = [Bar(day, *[Decimal("10")] * 4, 1000) for day in (date(2021, 11, 1), date(2026, 10, 6))]
    for symbol in (INDEX, *TW_STOCKS, *TRACKED_TW):
        await _store(session, "tw", symbol, bars, source="TWSE")


class Exchanges:
    """TWSE (an empty month) and Tiingo (one day), counting what each was asked."""

    def __init__(self, *, tw_down: bool = False, split: str | None = None):
        self.tw: list[str] = []
        self.us: list[str] = []
        self.tw_down = tw_down
        self.split = split

    async def twse(self, url, params):
        self.tw.append(INDEX if url == TWSE_INDEX_DAY else params["stockNo"])
        if self.tw_down:
            raise TimeoutError("TWSE did not answer")
        columns = price_history.INDEX_COLUMNS if url == TWSE_INDEX_DAY else price_history.COLUMNS
        return {"stat": "OK", "fields": list(columns), "data": []}

    async def tiingo(self, url, params):
        symbol = url.removeprefix(TIINGO_DAILY.split("{")[0]).split("/")[0]
        self.us.append(symbol)
        return [{**TIINGO_ROW, "splitFactor": 4.0 if symbol == self.split else 1.0}]


def keeper(exchanges: Exchanges, now: list[datetime]) -> PricesKeeper:
    return PricesKeeper(exchanges.twse, exchanges.tiingo, clock=lambda: now[0])


async def test_a_run_asks_a_few_and_pauses_seconds_not_hours(db_session, tracked, slept):
    await five_years_stored(db_session)
    exchanges, now = Exchanges(), [CLOCK_IN]

    await keeper(exchanges, now).refresh(db_session)

    # before: every stock, Tiingo's 75 seconds apart — 120 of them, two and a half hours
    assert len(US_STOCKS) + len(TRACKED_US) == 120 and 119 * 75 / 3600 > 2.4
    # now: Taiwan's ten (the index, the strip's seven, two tracked) and two of Tiingo's
    assert exchanges.tw == [INDEX, *TW_STOCKS, *TRACKED_TW]
    assert exchanges.us == ["NVDA", "AAPL"]
    assert sum(slept) == 9 * price_history.PAUSE_SECONDS + price_history.US_PAUSE  # 24.5 s
    read = await db_session.scalars(select(PriceFetch).where(PriceFetch.market.in_(("tw", "us"))))
    assert {(f.market, f.symbol) for f in read} == {
        *(("tw", s) for s in exchanges.tw),
        ("us", "NVDA"),
        ("us", "AAPL"),
    }


async def test_the_rest_are_the_next_runs_and_each_is_read_once_a_day(db_session, tracked, slept):
    await five_years_stored(db_session)
    exchanges, now = Exchanges(), [CLOCK_IN]
    prices = keeper(exchanges, now)
    await prices.refresh(db_session)

    now[0] += timedelta(minutes=5)
    exchanges.tw.clear()
    await prices.refresh(db_session)
    assert exchanges.tw == []  # Taiwan's day is read
    assert exchanges.us == ["NVDA", "AAPL", "GOOGL", "MSFT"]

    for _ in range(58):  # five hours of a shift's runs
        now[0] += timedelta(minutes=5)
        await prices.refresh(db_session)
    assert len(exchanges.us) == len(set(exchanges.us)) == 120  # each once
    now[0] += timedelta(minutes=5)
    await prices.refresh(db_session)
    assert len(exchanges.us) == 120  # nothing left today

    now[0] = CLOCK_IN + timedelta(days=1)  # the next day's 15:00: all again, in their order
    await prices.refresh(db_session)
    assert exchanges.tw == [INDEX, *TW_STOCKS, *TRACKED_TW]
    assert exchanges.us[-2:] == ["NVDA", "AAPL"]


async def test_an_exchange_s_bad_hour_ends_taiwan_s_part_and_is_tried_again(
    db_session, tracked, slept
):
    await five_years_stored(db_session)
    exchanges, now = Exchanges(tw_down=True), [CLOCK_IN]

    await keeper(exchanges, now).refresh(db_session)

    assert exchanges.tw == [INDEX]  # one not answered: the rest are the next run's
    assert exchanges.us == ["NVDA", "AAPL"]  # Tiingo's part all the same
    fetch = await db_session.scalar(select(PriceFetch).where(PriceFetch.symbol == INDEX))
    assert (fetch.fetched_at, fetch.next_at) == (None, CLOCK_IN + price_history.RETRY)
    # the next run asks the ones never asked first; the index after half an hour
    assert (await due(db_session, "tw", (INDEX, "2330"), CLOCK_IN))[0] == "2330"
    later = CLOCK_IN + price_history.RETRY
    assert await due(db_session, "tw", (INDEX,), later) == [INDEX]


async def test_a_stock_the_run_had_no_requests_left_for_is_the_next_run_s_first(
    db_session, tracked, slept
):
    await five_years_stored(db_session)
    bar = Bar(date(2026, 10, 1), *[Decimal("1")] * 4, 1)
    await _store(db_session, "us", "AAPL", [bar], source="Tiingo")
    exchanges, now = Exchanges(split="AAPL"), [CLOCK_IN]
    prices = keeper(exchanges, now)

    await prices.refresh(db_session)

    # AAPL's days carry a split: all five years again, a third request the run does not have
    assert exchanges.us == ["NVDA", "AAPL"]
    assert await db_session.scalar(select(PriceFetch).where(PriceFetch.symbol == "AAPL")) is None
    now[0] += timedelta(minutes=5)
    await prices.refresh(db_session)
    assert exchanges.us[2:] == ["AAPL", "AAPL"]  # first, and both its requests


async def test_read_waits_for_tomorrow_s_14_00_in_taipei(db_session):
    await asked(db_session, "us", "NVDA", CLOCK_IN, read=True)
    await asked(db_session, "us", "AAPL", CLOCK_IN - timedelta(hours=2), read=True)  # 13:00
    waits = dict((await db_session.execute(select(PriceFetch.symbol, PriceFetch.next_at))).all())
    assert waits["NVDA"] == datetime(2026, 10, 8, 6, 0, tzinfo=UTC)
    assert waits["AAPL"] == datetime(2026, 10, 7, 6, 0, tzinfo=UTC)  # before 14:00: today's
    assert await due(db_session, "us", ("NVDA", "AAPL", "MSFT"), CLOCK_IN) == ["MSFT", "AAPL"]
