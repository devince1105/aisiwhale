"""HD-10: an institution's quarter from its whole tables — the estimate worked out by hand, splits
and new CUSIPs, the 100 largest and the queue, and short runs."""

import json
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import select

from autora.domains.newsroom import institution_details
from autora.domains.newsroom.institution_details import (
    _move,
    _split,
    due,
    refresh_details,
    request,
    summarize,
    work_out,
)
from autora.domains.newsroom.models import InstitutionDetail, ThirteenFFiling
from autora.domains.newsroom.thirteenf import Holdings, Position
from autora.infra.http import FetchUnavailable
from tests.newsroom.test_thirteenf_tables import chunked, row, table

NOW = datetime(2026, 10, 7, 8, 0, tzinfo=UTC)
Q2, Q1 = date(2026, 6, 30), date(2026, 3, 31)


def holdings(*positions: Position) -> Holdings:
    h = Holdings(manager="", report_type="")
    for p in positions:
        h.positions[p.key] = p
    return h


def p(cusip, shares, value, *, name=None, kind="SH", put_call="", title="COM"):
    return Position(name or f"CO {cusip}", title, cusip, put_call, kind, shares, value)


# --- the estimate, by hand -----------------------------------------------------------------------


def test_the_estimate_worked_out_by_hand():
    before = holdings(
        p("AAAAAA101", 50, 400),  # A: 50 at $8
        p("CCCCCC103", 10, 300),  # C: sold out, 10 at $30
        p("DDDDDD104", 40, 800),  # D: 40 at $20, then a 2-for-1 split
        p("EEEEEE105", 10, 100),  # E: a new CUSIP for the same issuer and class next quarter
        p("HHHHHH108", 5, 50),  # H: unchanged shares, price up
    )
    now = holdings(
        p("AAAAAA101", 100, 1000),  # +50 at $10 = +500
        p("BBBBBB102", 20, 100),  # new: +100
        p("DDDDDD104", 84, 924),  # 2:1, so 80 → 84: +4 at $11 = +44
        p("EEEEEE204", 10, 100),  # E's new CUSIP: no estimate either side
        p("HHHHHH108", 5, 60),
        p("AAAAAA101", 1000, 999_999, put_call="PUT"),  # options and principal: not stocks
        p("NNNNNN109", 5000, 4900, kind="PRN"),
    )

    w = summarize(now, before)

    assert w.net_bought_usd == 500 + 100 - 300 + 44  # 344
    assert w.stock_value_usd == 1000 + 100 + 924 + 100 + 60  # 2,184
    assert w.value_usd == 2184 + 999_999 + 4900 and w.stocks == 5
    assert w.previous_stock_value_usd == 400 + 300 + 800 + 100 + 50
    assert w.counts == {
        "new": 2,
        "increased": 2,
        "decreased": 0,
        "sold_out": 2,
        "unchanged": 1,
        "uncertain": 2,
    }
    assert [(r["cusip"], r["weight_pct"]) for r in w.top] == [
        ("AAAAAA101", 45.79),
        ("DDDDDD104", 42.31),
        ("BBBBBB102", 4.58),  # 100 each: the CUSIP breaks the tie
        ("EEEEEE204", 4.58),
        ("HHHHHH108", 2.75),
    ]
    assert [(r["cusip"], r["traded_usd"]) for r in w.bought] == [
        ("AAAAAA101", 500),
        ("BBBBBB102", 100),
        ("DDDDDD104", 44),
    ]
    assert [(r["cusip"], r["traded_usd"], r["change"]) for r in w.sold] == [
        ("CCCCCC103", -300, "sold_out")
    ]
    d = next(r for r in w.top if r["cusip"] == "DDDDDD104")
    assert (d["split"], d["change"], d["previous_shares"]) == ("2:1", "increased", 40)
    e = next(r for r in w.top if r["cusip"] == "EEEEEE204")
    assert (e["change"], e["traded_usd"]) == ("new", None)


def test_without_the_quarter_before_there_is_no_estimate():
    w = summarize(holdings(p("AAAAAA101", 10, 100)), None)

    assert (w.net_bought_usd, w.counts, w.bought, w.sold) == (None, {}, [], [])
    assert w.top[0]["change"] is None and w.top[0]["weight_pct"] == 100.0


def test_the_nearest_split_and_a_market_that_moved():
    # KLA, 2026: 10-for-1, and the price doubled (301.71 against 1,472.41 / 10)
    assert _split(126_198_653, 12_596_207, Decimal("301.71") / Decimal("1472.41")) == (10, "10:1")
    kla = _move(
        p("482480100", 126_198_653, 38_075_000_000), p("482480100", 12_596_207, 18_546_000_000)
    )
    assert kla.split == "10:1" and 0 < kla.traded_usd < 100_000_000  # not US$34 billion
    # a reverse split, 1-for-7
    rev = _move(p("XXXXXX101", 10, 700), p("XXXXXX101", 70, 650))
    assert rev.split == "1:7" and rev.change == "unchanged" and rev.traded_usd == 0
    # tripled with no split that fits: the market, and the shares bought
    marvell = _move(p("573874104", 134, 40_200), p("573874104", 100, 10_000))
    assert marvell.split is None and marvell.traded_usd == 34 * 300


# --- reading and keeping a quarter ---------------------------------------------------------------

ARCHIVES = "https://www.sec.gov/Archives/edgar/data"


def filing(cik, accession, period, *, filed, value, entries=2, form="13F-HR", amendment=None):
    return ThirteenFFiling(
        accession=accession,
        cik=cik,
        company="ACME CAPITAL",
        form=form,
        filed=filed,
        period=period,
        manager="Acme Capital",
        amendment=amendment,
        report_type="13F HOLDINGS REPORT",
        entries=entries,
        value_usd=value,
        read_at=NOW,
        attempts=0,
        scale=1,
        scale_attempts=0,
    )


def sec(tables: dict[tuple[str, str], bytes]):
    """SEC as a few filings: each folder's listing (``fetch``) and its table (``chunks``)."""
    listings, bodies = {}, {}
    for (cik, accession), body in tables.items():
        folder = f"{ARCHIVES}/{cik}/{accession.replace('-', '')}"
        listings[f"{folder}/index.json"] = json.dumps(
            {"directory": {"item": [{"name": "primary_doc.xml"}, {"name": "infotable.xml"}]}}
        ).encode()
        bodies[f"{folder}/infotable.xml"] = body

    async def fetch(url: str) -> bytes:
        return listings[url]

    return fetch, chunked(bodies)


async def test_a_quarter_is_read_whole_against_the_one_before_and_kept(db_session):
    db_session.add_all(
        [
            filing("9001", "0000009001-26-000002", Q2, filed=date(2026, 8, 10), value=1000),
            # the quarter before: its total in thousands, as its rows are (5 is US$5,000)
            filing("9001", "0000009001-26-000001", Q1, filed=date(2026, 5, 10), value=5),
        ]
    )
    await db_session.flush()
    # the quarter before filed in thousands: its shares come out worth under a dollar each
    fetch, chunks = sec(
        {
            ("9001", "0000009001-26-000002"): table(row("A", "AAAAAA101", 1000, 100)),
            ("9001", "0000009001-26-000001"): table(
                row("A", "AAAAAA101", 4, 500), row("B", "BBBBBB102", 1, 1000)
            ),
        }
    )

    detail = await work_out(db_session, fetch, chunks, "0009001", Q2, now=NOW)

    assert (detail.status, detail.cik, detail.previous_period) == ("ready", "9001", Q1)
    assert detail.accessions == ["0000009001-26-000002"]
    assert (int(detail.stock_value_usd), int(detail.previous_stock_value_usd)) == (1000, 5000)
    # A: 500 → 100 shares at $10 = −4,000; B sold out, 1,000 shares worth US$1,000
    assert int(detail.net_bought_usd) == -4000 - 1000
    assert detail.counts["decreased"] == 1 and detail.counts["sold_out"] == 1
    before = await db_session.get(ThirteenFFiling, "0000009001-26-000001")
    assert before.scale == 1000  # learnt from its whole table
    assert detail.computed_at == NOW


async def test_a_quarter_that_cannot_be_read_fails_after_three_tries(db_session):
    db_session.add(filing("9002", "0000009002-26-000001", Q2, filed=date(2026, 8, 10), value=1))
    await db_session.flush()
    fetch, chunks = sec({("9002", "0000009002-26-000001"): b"<informationTable><infoTable>"})

    for _ in range(3):
        detail = await work_out(db_session, fetch, chunks, "9002", Q2, now=NOW)

    assert (detail.status, detail.attempts) == ("failed", 3)
    assert "could not be read" in detail.error


async def test_sec_answering_slowly_keeps_nothing(db_session):
    db_session.add(filing("9003", "0000009003-26-000001", Q2, filed=date(2026, 8, 10), value=1))
    await db_session.flush()

    async def slow(url: str) -> bytes:
        raise FetchUnavailable(f"{url} answered 503")

    async def no_chunks(url: str):
        raise FetchUnavailable(url)
        yield b""

    done = await refresh_details(db_session, slow, no_chunks, today=date(2026, 10, 7))

    assert done == 0
    detail = await db_session.get(InstitutionDetail, ("9003", Q2))
    assert detail is None or detail.attempts == 0


# --- what is due ---------------------------------------------------------------------------------


async def test_asked_for_first_then_the_largest_without_one(db_session):
    db_session.add_all(
        [
            filing("1", "0000000001-26-000001", Q2, filed=date(2026, 8, 1), value=300),
            filing("2", "0000000002-26-000001", Q2, filed=date(2026, 8, 1), value=200),
            filing("3", "0000000003-26-000001", Q2, filed=date(2026, 8, 1), value=100),
            filing("4", "0000000004-26-000001", Q2, filed=date(2026, 8, 1), value=50),
        ]
    )
    await db_session.flush()
    await request(db_session, "4", Q2, now=NOW)
    await request(db_session, "3", Q2, now=datetime(2026, 10, 7, 7, 0, tzinfo=UTC))
    # 1 is worked out already from its filing; 2 from an older one (an amendment came since)
    db_session.add_all(
        [
            InstitutionDetail(
                cik="1", period=Q2, status="ready", accessions=["0000000001-26-000001"]
            ),
            InstitutionDetail(cik="2", period=Q2, status="ready", accessions=["older"]),
        ]
    )
    await db_session.flush()

    assert await due(db_session, Q2, ranked=3) == ["3", "4", "2"]


async def test_a_request_is_kept_once(db_session):
    first = await request(db_session, "0001234", Q2, now=NOW)
    again = await request(db_session, "1234", Q2, now=datetime(2026, 10, 8, tzinfo=UTC))

    assert (first.cik, first.status, again.requested_at) == ("1234", "queued", NOW)
    rows = (await db_session.scalars(select(InstitutionDetail))).all()
    assert len(rows) == 1


async def test_a_run_stops_starting_institutions_when_its_time_is_up(db_session, monkeypatch):
    for n in range(1, 4):
        db_session.add(
            filing(str(n), f"000000000{n}-26-000001", Q2, filed=date(2026, 8, 1), value=100 * n)
        )
    await db_session.flush()
    fetch, chunks = sec(
        {
            (str(n), f"000000000{n}-26-000001"): table(row("A", "AAAAAA101", 1000, 100))
            for n in range(1, 4)
        }
    )
    ticks = iter([0.0, 0.0, 10.0, 99.0, 99.0])  # start; first; second; then past the budget

    done = await refresh_details(
        db_session, fetch, chunks, today=date(2026, 10, 7), budget=45, clock=lambda: next(ticks)
    )

    assert done == 2
    ready = (await db_session.scalars(select(InstitutionDetail.cik))).all()
    assert sorted(ready) == ["2", "3"]  # the largest first
    assert institution_details.RANKED == 100
