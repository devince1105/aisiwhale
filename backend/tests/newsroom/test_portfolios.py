"""HD-04: the holdings dashboard's cards — a simulated one-year return worked out by hand, the
13Fs' own prices, Tiingo where they cannot answer (a split, a stock nobody holds any more), the
latest quotes, the biggest moves."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from autora.domains.newsroom import portfolios
from autora.domains.newsroom.markets import edgar_13f
from autora.domains.newsroom.models import (
    CusipSymbol,
    PortfolioPosition,
    PortfolioQuarter,
    PortfolioStat,
    PriceAsk,
    RawClose,
    Source,
    StockQuote,
)
from autora.domains.newsroom.portfolios import (
    Close,
    Held,
    Prices,
    Quarter,
    Quote,
    moves,
    refresh_portfolio_stats,
    simulate,
    year_start,
)
from tests.conftest import unique_company

TODAY = date(2026, 10, 6)
Q0, Q1, Q2, Q3 = date(2025, 9, 30), date(2025, 12, 31), date(2026, 3, 31), date(2026, 6, 30)


def held(cusip, shares, price):
    return Held(cusip, f"{cusip} INC", shares, int(shares * price))


# A and B, 60/40 at 100 each; A +10%, B −10%; then both +10%; then flat; then both +10% to the
# latest quotes. 1.02 × 1.1 × 1.0 × 1.1 = 1.2342.
BOOK = [
    Quarter(Q0, date(2025, 11, 14), (held("A", 6, 100), held("B", 4, 100))),
    Quarter(Q1, date(2026, 2, 17), (held("A", 6, 110), held("B", 4, 90))),
    Quarter(Q2, date(2026, 5, 15), (held("A", 6, 121), held("B", 4, 99))),
    Quarter(Q3, date(2026, 8, 14), (held("A", 6, 121), held("B", 4, 99))),
]
QUOTES = {
    "AAA": Quote(Decimal("133.1"), date(2026, 10, 5)),
    "BBB": Quote(Decimal("108.9"), date(2026, 10, 5)),
}


def implied(book):
    return {(h.cusip, q.period): Decimal(h.value) / h.shares for q in book for h in q.held}


def test_a_year_starts_at_the_last_quarter_s_end_a_year_ago():
    assert year_start(TODAY) == Q0
    assert year_start(date(2026, 1, 5)) == date(2024, 12, 31)
    assert year_start(date(2026, 3, 31)) == date(2025, 3, 31), "a quarter's end is its own"


def test_the_quarters_compound_from_the_13fs_own_prices():
    prices = Prices(implied(BOOK), {"A": "AAA", "B": "BBB"}, quotes=dict(QUOTES))
    result = simulate(BOOK, prices, TODAY)
    assert result.growth == pytest.approx(Decimal("0.2342"), abs=Decimal("1e-9"))
    assert (result.start, result.through, result.coverage) == (Q0, date(2026, 10, 5), 1)
    assert prices.needs == {}, "nothing asked of Tiingo: every move inside CHECK"
    assert prices.quoted == {"AAA", "BBB"}


def split_book():
    """B splits 2 for 1 between Q1 and Q2: its 13F price halves and its shares double."""
    return [
        BOOK[0],
        BOOK[1],
        Quarter(Q2, BOOK[2].filed, (held("A", 6, 121), held("B", 8, Decimal("49.5")))),
        Quarter(Q3, BOOK[3].filed, (held("A", 6, 121), held("B", 8, Decimal("49.5")))),
    ]


def test_a_split_is_asked_of_tiingo_and_until_then_left_out():
    book = split_book()
    quotes = {**QUOTES, "BBB": Quote(Decimal("54.45"), date(2026, 10, 5))}
    prices = Prices(implied(book), {"A": "AAA", "B": "BBB"}, quotes=quotes)
    waiting = simulate(book, prices, TODAY)
    assert waiting.coverage == pytest.approx(Decimal(660) / 1020)
    assert (waiting.growth, waiting.pending) == (None, 1), "waiting for Tiingo: no number"
    assert list(prices.needs) == [("BBB", Q1, Q2)]

    prices.closes["BBB"] = [
        Close(date(2025, 12, 31), Decimal(90)),
        Close(date(2026, 2, 16), Decimal(50), Decimal(2)),  # the split's day
        Close(date(2026, 3, 31), Decimal("49.5")),
    ]
    result = simulate(book, prices, TODAY)
    assert result.growth == pytest.approx(Decimal("0.2342"), abs=Decimal("1e-9"))
    assert (result.coverage, result.pending) == (1, 0)


def test_waiting_for_the_biggest_moves_would_bend_the_number_so_none_is_given():
    """Coverage alone is not enough: the stretches Tiingo is asked about are the biggest moves,
    and a number without them is not a smaller sample of the same portfolio."""
    book = [
        BOOK[0],
        Quarter(Q1, BOOK[1].filed, (held("A", 6, 110), held("B", 4, 90), held("W", 2, 100))),
        Quarter(Q2, BOOK[2].filed, (held("A", 6, 121), held("B", 4, 99), held("W", 2, 300))),
        Quarter(Q3, BOOK[3].filed, (held("A", 6, 121), held("B", 4, 99), held("W", 2, 300))),
    ]
    quotes = {**QUOTES, "WWW": Quote(Decimal(330), date(2026, 10, 5))}
    prices = Prices(implied(book), {"A": "AAA", "B": "BBB", "W": "WWW"}, quotes=quotes)
    result = simulate(book, prices, TODAY)
    assert result.coverage > portfolios.MIN_COVERAGE, "W tripled: 200 of the quarter's 1,220"
    assert (result.growth, result.pending) == (None, 1)


def test_a_stretch_tiingo_could_not_answer_is_not_waited_for():
    book = [Quarter(Q0, BOOK[0].filed, (held("A", 6, 100), held("C", 4, 100))), *BOOK[1:]]
    prices = Prices(implied(book), {"A": "AAA", "B": "BBB", "C": "CCC"}, quotes=dict(QUOTES))
    prices.asked = {("CCC", Q0, Q1)}
    result = simulate(book, prices, TODAY)
    assert (prices.needs, result.pending) == ({}, 0)
    assert result.coverage == pytest.approx(Decimal("0.6")), "C left out, not waited for"


def test_a_stock_that_stopped_trading_was_cash_at_its_last_close():
    """Taken over within the quarter: Tiingo's closes end before the quarter does."""
    book = [Quarter(Q0, BOOK[0].filed, (held("A", 6, 100), held("C", 4, 100))), *BOOK[1:]]
    prices = Prices(implied(book), {"A": "AAA", "B": "BBB", "C": "CCC"}, quotes=dict(QUOTES))
    prices.asked = {("CCC", Q0, Q1)}
    prices.closes["CCC"] = [Close(Q0, Decimal(100)), Close(date(2025, 11, 20), Decimal(125))]
    assert prices.stretch("C", Q0, Q1, Decimal("0.4"), ask=True) == Decimal("1.25")
    assert simulate(book, prices, TODAY).coverage == 1


def test_a_stock_sold_out_that_nobody_holds_is_priced_by_tiingo():
    book = [Quarter(Q0, BOOK[0].filed, (held("A", 6, 100), held("C", 4, 100))), *BOOK[1:]]
    prices = Prices(implied(book), {"A": "AAA", "B": "BBB", "C": "CCC"}, quotes=dict(QUOTES))
    simulate(book, prices, TODAY)
    assert ("CCC", Q0, Q1) in prices.needs
    prices.closes["CCC"] = [Close(Q0, Decimal(100)), Close(date(2025, 12, 31), Decimal(90))]
    assert simulate(book, prices, TODAY).coverage == 1


def test_a_big_move_since_the_quarter_is_checked_for_a_split_since():
    # B splits 2 for 1 after Q3: its quote is half its 13F price
    prices = Prices(
        implied(BOOK),
        {"A": "AAA", "B": "BBB"},
        quotes={**QUOTES, "BBB": Quote(Decimal("54.45"), date(2026, 10, 5))},
    )
    assert simulate(BOOK, prices, TODAY).growth is None
    assert ("BBB", Q3, None) in prices.needs
    prices.closes["BBB"] = [
        Close(Q3, Decimal(99)),
        Close(date(2026, 9, 1), Decimal(50), Decimal(2)),
        Close(date(2026, 10, 2), Decimal("54.4")),
    ]
    assert simulate(BOOK, prices, TODAY).growth == pytest.approx(
        Decimal("0.2342"), abs=Decimal("1e-9")
    )
    # a quote far from the last close kept: a split since may have come between — asked again
    prices.quotes["BBB"] = Quote(Decimal("27"), date(2026, 10, 5))
    prices.needs.clear()
    simulate(BOOK, prices, TODAY)
    assert ("BBB", Q3, None) in prices.needs


def test_no_number_without_a_year_of_13fs_or_the_latest_prices():
    prices = Prices(implied(BOOK), {"A": "AAA", "B": "BBB"}, quotes=dict(QUOTES))
    assert simulate(BOOK[2:], prices, TODAY).growth is None, "less than a year kept"
    no_quotes = Prices(implied(BOOK), {"A": "AAA", "B": "BBB"})
    assert simulate(BOOK, no_quotes, TODAY).growth is None


def test_only_the_top_ninety_percent_is_asked_about():
    small = Quarter(Q3, BOOK[3].filed, (held("A", 95, 10), held("Z", 5, 10)))
    prices = Prices(implied([*BOOK[:3], small]), {"A": "AAA", "Z": "ZZZ"})
    simulate([*BOOK[:3], small], prices, TODAY)
    assert "ZZZ" not in prices.quoted


def test_the_biggest_moves_and_a_split_that_is_not_one():
    before = Quarter(Q2, BOOK[2].filed, (held("A", 6, 121), held("B", 4, 99), held("E", 3, 100)))
    now = Quarter(Q3, BOOK[3].filed, (held("D", 5, 100), held("A", 8, 121), held("B", 3, 99)))
    prices = Prices(implied([before, now]), {})
    got = moves(now, before, prices)
    assert [(m.cusip, m.change, m.value_change) for m in got] == [
        ("D", "new", 500),
        ("E", "sold_out", -300),
    ]
    assert [m.change for m in moves(now, before, prices, count=4)][2:] == ["increased", "decreased"]

    split = Quarter(Q3, BOOK[3].filed, (held("B", 8, Decimal("49.5")),))
    one = Quarter(Q2, BOOK[2].filed, (held("B", 4, 99),))
    prices = Prices(implied([one, split]), {"B": "BBB"})
    assert moves(split, one, prices) == [], "it may have split: not a move until Tiingo says"
    prices.closes["BBB"] = [
        Close(Q2, Decimal(99)),
        Close(date(2026, 5, 1), Decimal(50), Decimal(2)),
        Close(Q3, Decimal("49.5")),
    ]
    assert moves(split, one, prices) == [], "two for one: the same holding"


# --- the run, against the database --------------------------------------------------------------


@pytest.fixture
async def book(db_session):
    company = await unique_company(db_session)
    source = Source(
        company_id=company.id,
        name="SEC 13F：test",
        kind="rss",
        url=edgar_13f("0000000001"),
        config={"title_prefix": "測試（Test Capital）", "primary": True, "section": "holdings"},
    )
    db_session.add(source)
    await db_session.flush()
    for quarter in split_book():
        row = PortfolioQuarter(
            company_id=company.id,
            source_id=source.id,
            period=quarter.period,
            filed=quarter.filed,
            filings=[{"cik": "1", "accession": f"0000000001-26-{quarter.period:%m%d}00"}],
            total_value_usd=quarter.value,
        )
        db_session.add(row)
        await db_session.flush()
        for h in quarter.held:
            db_session.add(
                PortfolioPosition(
                    quarter_id=row.id,
                    cusip=h.cusip,
                    issuer=h.issuer,
                    title_of_class="COM",
                    kind="SH",
                    amount=h.shares,
                    value_usd=h.value,
                )
            )
        # an option is not a holding the return counts
        db_session.add(
            PortfolioPosition(
                quarter_id=row.id,
                cusip="A",
                issuer="A INC",
                title_of_class="COM",
                put_call="PUT",
                kind="SH",
                amount=1000,
                value_usd=999_999,
            )
        )
    now = datetime(2026, 10, 6, tzinfo=UTC)
    db_session.add_all(
        [
            CusipSymbol(cusip="A", symbol="AAA", checked_at=now),
            CusipSymbol(cusip="B", symbol="BBB", checked_at=now),
        ]
    )
    await db_session.flush()
    return company, source


class Finnhub:
    def __init__(self):
        self.asked: list[str] = []

    async def __call__(self, symbol):
        self.asked.append(symbol)
        return {"AAA": QUOTES["AAA"], "BBB": Quote(Decimal("54.45"), date(2026, 10, 5))}.get(symbol)


class Tiingo:
    def __init__(self):
        self.asked: list[tuple[str, dict]] = []

    async def __call__(self, url, params):
        self.asked.append((url, params))
        assert "/BBB/" in url and params["startDate"] <= "2025-12-31"
        return [
            {"date": "2025-12-31T00:00:00.000Z", "close": 90, "splitFactor": 1.0},
            {"date": "2026-02-16T00:00:00.000Z", "close": 50, "splitFactor": 2.0},
            {"date": "2026-03-31T00:00:00.000Z", "close": 49.5, "splitFactor": 1.0},
        ]


async def test_the_run_writes_the_card_and_asks_tiingo_once(db_session, book):
    company, source = book
    finnhub, tiingo = Finnhub(), Tiingo()
    run = dict(quote=finnhub, tiingo=tiingo, today=TODAY, quote_pause=0, tiingo_pause=0)
    assert await refresh_portfolio_stats(db_session, company.id, **run) == 1
    card = await db_session.get(PortfolioStat, source.id)
    assert float(card.return_pct) == pytest.approx(0.2342)
    assert (card.return_start, card.return_through, float(card.coverage)) == (
        Q0,
        date(2026, 10, 5),
        1.0,
    )
    assert (card.period, int(card.long_value_usd), card.pending) == (Q3, 1122, 0)
    assert [(h["symbol"], round(h["weight"], 4)) for h in card.holdings] == [
        ("AAA", 0.6471),
        ("BBB", 0.3529),
    ]
    assert card.moves == [], "Q3 holds what Q2 did"
    assert [(p["symbol"], p["change"], p["value_usd"]) for p in card.positions] == [
        ("AAA", "unchanged", 726),
        ("BBB", "unchanged", 396),
    ]  # HD-05: the person page's table
    assert [(st["start"], st["end"], st["growth"]) for st in card.stretches] == [
        ("2025-09-30", "2025-12-31", 1.02),
        ("2025-12-31", "2026-03-31", 1.1),
        ("2026-03-31", "2026-06-30", 1.0),
        ("2026-06-30", "2026-10-05", 1.1),
    ]
    assert sorted(finnhub.asked) == ["AAA", "BBB"] and len(tiingo.asked) == 1
    kept = (await db_session.scalars(select(RawClose).where(RawClose.symbol == "BBB"))).all()
    assert len(kept) == 3
    asked = (await db_session.scalars(select(PriceAsk).where(PriceAsk.symbol == "BBB"))).all()
    assert [(a.start, a.end) for a in asked] == [(Q1, Q2)]

    # the closes and the quotes are kept: the next run asks Tiingo nothing, Finnhub nothing
    again = Tiingo()
    await refresh_portfolio_stats(db_session, company.id, **{**run, "tiingo": again})
    assert again.asked == [] and sorted(finnhub.asked) == ["AAA", "BBB"]


async def test_a_run_asks_a_few_quotes_the_missing_first_and_old_ones_again(db_session, book):
    """A scheduler handler holds up everything else the worker starts: a run is short."""
    company, _ = book
    first = Finnhub()
    run = dict(tiingo=None, today=TODAY, quote_pause=0, quotes_per_run=1)
    await refresh_portfolio_stats(db_session, company.id, quote=first, **run)
    await refresh_portfolio_stats(db_session, company.id, quote=first, **run)
    assert first.asked == ["AAA", "BBB"], "one a run, each asked once"
    later = datetime.now(UTC) + portfolios.QUOTE_AGE + timedelta(hours=1)
    await refresh_portfolio_stats(db_session, company.id, quote=first, now=later, **run)
    assert first.asked[2:] == ["AAA"], "old: asked again, the oldest first"
    kept = await db_session.get(StockQuote, "BBB")
    assert kept.price == Decimal("54.45") and kept.day == date(2026, 10, 5)


async def test_without_tiingo_the_split_quarter_leaves_no_number(db_session, book):
    company, source = book
    run = dict(quote=Finnhub(), tiingo=None, today=TODAY, quote_pause=0)
    await refresh_portfolio_stats(db_session, company.id, **run)
    card = await db_session.get(PortfolioStat, source.id)
    assert card.return_pct is None and float(card.coverage) < float(portfolios.MIN_COVERAGE)
    assert card.pending == 1, "the split quarter, waiting: the site says 整理中"
    assert card.holdings[0]["symbol"] == "AAA", "the rest of the card is there"


async def test_a_stretch_tiingo_had_nothing_for_is_not_asked_again(db_session, book):
    company, source = book

    class Empty(Tiingo):
        async def __call__(self, url, params):
            self.asked.append((url, params))
            return []

    empty = Empty()
    run = dict(quote=Finnhub(), today=TODAY, quote_pause=0, tiingo_pause=0)
    await refresh_portfolio_stats(db_session, company.id, tiingo=empty, **run)
    await refresh_portfolio_stats(db_session, company.id, tiingo=empty, **run)
    assert len(empty.asked) == 1, "asked once; within RETRY it is not asked again"
    card = await db_session.get(PortfolioStat, source.id)
    assert card.pending == 0 and card.return_pct is None, "no price, left out, not waited for"
