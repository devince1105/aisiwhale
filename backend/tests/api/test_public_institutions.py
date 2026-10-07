"""HD-11: 機構排行 and an institution's page — every filer's quarter in dollars and named as Taiwan
writes it, searched and sorted; a page's ten largest holdings for anybody, the rest and its buys
and sells signed in (D-159), and one never opened queued."""

from datetime import UTC, date, datetime

import httpx
import pytest
from sqlalchemy import select

from autora.domains.newsroom import rankings
from autora.domains.newsroom.models import CusipSymbol, InstitutionDetail, ThirteenFFiling
from tests.api.readers import sign_in

Q2, Q1 = date(2026, 6, 30), date(2026, 3, 31)
NOW = datetime(2026, 10, 7, 8, 0, tzinfo=UTC)
RANKING = "/api/public/institutions"


@pytest.fixture
async def public(api):
    async with httpx.AsyncClient(transport=api._transport, base_url="http://test") as client:
        yield client


@pytest.fixture(autouse=True)
def few_filers(monkeypatch):
    monkeypatch.setattr(rankings, "MIN_FILERS", 1)  # a test's quarter has three filers, not 9,000
    rankings.forget()
    yield
    rankings.forget()


def filing(cik, n, period, value, *, entries=100, scale=1, manager=None, filed=None):
    return ThirteenFFiling(
        accession=f"{int(cik):010d}-26-{n:06d}",
        cik=cik,
        company=manager or f"FILER {cik}",
        form="13F-HR",
        filed=filed or (date(2026, 8, 10) if period == Q2 else date(2026, 5, 10)),
        period=period,
        manager=manager or f"FILER {cik}",
        report_type="13F HOLDINGS REPORT",
        entries=entries,
        value_usd=value,
        read_at=NOW,
        attempts=0,
        scale=scale,
        scale_attempts=0,
    )


@pytest.fixture
async def quarters(db_session):
    db_session.add_all(
        [
            # BlackRock: largest, up from the first quarter
            filing("2012383", 1, Q2, 6_000, manager="BlackRock, Inc."),
            filing("2012383", 2, Q1, 5_000, manager="BlackRock, Inc."),
            # T. Rowe Price: filed in thousands, so 5 is US$5,000; down from 5,500
            filing("80255", 3, Q2, 5, scale=1000, manager="PRICE T ROWE ASSOCIATES INC /MD/"),
            filing("80255", 4, Q1, 5_500, manager="PRICE T ROWE ASSOCIATES INC /MD/"),
            # a newcomer, not yet checked for thousands, filed last
            filing("9999999", 5, Q2, 100, scale=None, filed=date(2026, 8, 14)),
        ]
    )
    await db_session.flush()


async def test_the_ranking_in_dollars_named_and_compared(public, quarters):
    answer = await public.get(RANKING, params={"lang": "zh-TW"})

    assert answer.status_code == 200, answer.text
    assert answer.headers["cache-control"] == "public, max-age=600"
    page = answer.json()
    assert (page["period"], page["previous_period"], page["periods"]) == (
        "2026-06-30",
        "2026-03-31",
        ["2026-06-30", "2026-03-31"],
    )
    assert (page["filers"], page["total"]) == (3, 3)
    shown = [
        (r["rank"], r["name"], r["value_usd"], r["change_usd"], r["in_thousands"], r["in_doubt"])
        for r in page["rows"]
    ]
    assert shown == [
        (1, "貝萊德", 6000, 1000, False, False),
        (2, "普徠仕", 5000, -500, True, False),
        (3, "FILER 9999999", 100, None, False, True),
    ]
    assert page["rows"][0]["change_pct"] == 20.0 and page["rows"][1]["change_pct"] == -9.09
    english = (await public.get(RANKING, params={"lang": "en"})).json()
    assert english["rows"][0]["name"] == "BlackRock"


async def test_searched_sorted_and_a_page_at_a_time(public, quarters):
    async def get(**params):
        page = (await public.get(RANKING, params={"lang": "zh-TW", **params})).json()
        return [(r["rank"], r["name"]) for r in page["rows"]], page["total"]

    assert await get(q="普徠仕") == ([(2, "普徠仕")], 1)  # the rank is the quarter's
    assert await get(q="rowe price") == ([(2, "普徠仕")], 1)  # the filed name, any case
    assert await get(q="9999999") == ([(3, "FILER 9999999")], 1)
    assert (await get(sort="change"))[0] == [(1, "貝萊德"), (2, "普徠仕"), (3, "FILER 9999999")]
    assert (await get(sort="change", order="asc"))[0][0] == (2, "普徠仕")  # none-changed last
    assert (await get(sort="filed"))[0][0] == (3, "FILER 9999999")
    assert (await get(limit=1, offset=1)) == ([(2, "普徠仕")], 3)
    # a quarter nobody can ask for is the default one
    assert (await public.get(RANKING, params={"lang": "zh-TW", "period": "2020-03-31"})).json()[
        "period"
    ] == "2026-06-30"


def detail(cik, rows=12):
    top = [
        {
            "cusip": f"C{i:08d}",
            "name": "APPLE INC" if i == 0 else f"ISSUER {i}",
            "title_of_class": "COM",
            "change": "increased",
            "shares": 200,
            "previous_shares": 100,
            "value_usd": 1000 - i,
            "previous_value_usd": 500,
            "weight_pct": 10.0,
            "traded_usd": 500,
            "split": None,
        }
        for i in range(rows)
    ]
    return InstitutionDetail(
        cik=cik,
        period=Q2,
        status="ready",
        computed_at=NOW,
        accessions=[f"{int(cik):010d}-26-000001"],
        previous_period=Q1,
        stock_value_usd=6000,
        previous_stock_value_usd=5000,
        stocks=rows,
        net_bought_usd=750,
        counts={"increased": rows},
        top=top,
        bought=top[:3],
        sold=[{**top[5], "change": "sold_out", "traded_usd": -250, "shares": 0}],
    )


async def test_ten_largest_for_anybody_the_rest_signed_in(public, quarters, db_session):
    db_session.add_all(
        [detail("2012383"), CusipSymbol(cusip="C00000000", symbol="AAPL", checked_at=NOW)]
    )
    await db_session.flush()
    path = f"{RANKING}/0002012383"

    stranger = await public.get(path, params={"lang": "zh-TW"})

    assert stranger.status_code == 200, stranger.text
    assert stranger.headers["cache-control"] == "private, no-store"
    page = stranger.json()
    assert (page["cik"], page["name"], page["rank"], page["status"]) == (
        "2012383",
        "貝萊德",
        1,
        "ready",
    )
    assert (page["value_usd"], page["previous_value_usd"], page["change_usd"]) == (6000, 5000, 1000)
    assert (len(page["top"]), page["top_total"], page["locked"]) == (10, 12, True)
    assert (page["bought"], page["sold"]) == ([], [])
    assert page["top"][0]["symbol"] == "AAPL" and page["top"][0]["name"] == "蘋果"
    assert page["filings"][0]["url"].endswith("0002012383-26-000001-index.htm")
    assert page["net_bought_usd"] == 750

    await sign_in(public, "institutions-reader@example.com")
    page = (await public.get(path, params={"lang": "zh-TW"})).json()
    assert (len(page["top"]), page["locked"]) == (12, False)
    assert [r["traded_usd"] for r in page["sold"]] == [-250] and len(page["bought"]) == 3


async def test_an_institution_never_opened_is_queued(public, quarters, db_session):
    page = (await public.get(f"{RANKING}/80255", params={"lang": "en"})).json()

    assert (page["name"], page["status"], page["top"], page["locked"]) == (
        "T. Rowe Price",
        "queued",
        [],
        False,
    )
    assert page["in_thousands"] and page["value_usd"] == 5000
    queued = (await db_session.scalars(select(InstitutionDetail))).all()
    assert [(d.cik, d.period, d.status) for d in queued] == [("80255", Q2, "queued")]


async def test_no_13f_no_page(public, quarters):
    assert (await public.get(f"{RANKING}/123", params={"lang": "zh-TW"})).status_code == 404
    assert (await public.get(f"{RANKING}/abc", params={"lang": "zh-TW"})).status_code == 422
