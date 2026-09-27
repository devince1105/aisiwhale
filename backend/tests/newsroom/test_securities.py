"""D-061: every listed Taiwan and US stock, to look one up; and which ones readers asked about."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import delete

from autora.domains.newsroom import securities
from autora.domains.newsroom.models import Security, TrackedSecurity

TWSE_ALL = [
    {"Code": "1101", "Name": "台泥"},
    {"Code": "0050", "Name": "元大台灣50"},
    {"Code": "00631L", "Name": "元大台灣50正2"},
    {"Code": "030001", "Name": "某權證"},  # a warrant: not a stock
]
COMPANIES = [{"公司代號": "1101", "英文簡稱": "TCC"}]
TPEX_ALL = [
    {"SecuritiesCompanyCode": "6488", "CompanyName": "環球晶"},
    {"SecuritiesCompanyCode": "73011P", "CompanyName": "某權證"},
]
US = [
    {"symbol": "NVDA", "description": "NVIDIA CORP", "type": "Common Stock", "mic": "XNAS"},
    {"symbol": "SPY", "description": "SS SPDR S&P 500 ETF TRUST-US", "type": "ETP", "mic": "ARCX"},
    {"symbol": "BRK.B", "description": "BERKSHIRE HATHAWAY", "type": "Common Stock", "mic": "XNYS"},
    {"symbol": "PINKY", "description": "SOME OTC CO", "type": "Common Stock", "mic": "OOTC"},
    {"symbol": "ABCW", "description": "A WARRANT", "type": "Equity WRT", "mic": "XNAS"},
]  # fmt: skip


def test_the_lists_keep_stocks_funds_and_adrs_and_leave_the_rest():
    tw = securities.twse_listed(TWSE_ALL, COMPANIES)
    assert [(s.symbol, s.kind, s.name_en) for s in tw] == [
        ("1101", "stock", "TCC"), ("0050", "etf", None), ("00631L", "etf", None)
    ]  # fmt: skip
    assert [s.symbol for s in securities.tpex_listed(TPEX_ALL)] == ["6488"]
    assert [(s.symbol, s.kind) for s in securities.us_listed(US)] == [
        ("NVDA", "stock"), ("SPY", "etf"), ("BRK.B", "stock")
    ]  # fmt: skip


def test_a_symbol_s_shape_says_its_market():
    assert securities.market_of("2330") == "tw" and securities.market_of("00631l") == "tw"
    assert securities.market_of("brk.b") == "us" and securities.market_of("NVDA") == "us"
    assert securities.market_of("../x") is None


async def _listed(db_session):
    await db_session.execute(delete(Security))
    await securities.store(
        db_session,
        securities.twse_listed(TWSE_ALL, COMPANIES)
        + securities.tpex_listed(TPEX_ALL)
        + securities.us_listed(US),
    )


async def test_a_stock_is_found_by_code_ticker_or_name(db_session):
    await _listed(db_session)
    assert [s.symbol for s in await securities.search(db_session, "nvda")] == ["NVDA"]
    assert [s.symbol for s in await securities.search(db_session, "台泥")] == ["1101"]
    assert [s.symbol for s in await securities.search(db_session, "tcc")] == ["1101"]
    assert [s.symbol for s in await securities.search(db_session, "0050")][0] == "0050"
    assert [s.symbol for s in await securities.search(db_session, "berkshire")] == ["BRK.B"]
    assert await securities.search(db_session, "  ") == []


async def test_a_page_s_symbol_finds_the_strip_s_stock_or_a_listed_one(db_session):
    await _listed(db_session)
    curated = await securities.find(db_session, "nvda")
    assert curated.cusips  # the strip's, with its 13F CUSIP
    listed = await securities.find(db_session, "6488")
    assert (listed.market, listed.zh, listed.cusips) == ("tw", "環球晶", ())
    assert (await securities.find(db_session, "brk.b")).symbol == "BRK.B"
    assert await securities.find(db_session, "9999") is None


async def test_a_stock_asked_about_is_tracked_for_thirty_days(db_session):
    await _listed(db_session)
    await db_session.execute(delete(TrackedSecurity))
    now = datetime(2026, 9, 27, tzinfo=UTC)
    stock = await securities.find(db_session, "6488")
    await securities.track(db_session, stock, now=now - timedelta(days=40))
    assert await securities.tracked(db_session, "tw", now=now) == []
    await securities.track(db_session, stock, now=now)  # asked again: tracked again
    assert await securities.tracked(db_session, "tw", now=now) == ["6488"]
    assert await securities.exchange_of(db_session, ["6488", "1101"]) == {
        "6488": "TPEx", "1101": "TWSE"
    }  # fmt: skip
