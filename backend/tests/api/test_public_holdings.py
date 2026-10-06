"""HD-05: the holdings dashboard's API — the cards, a person page (its table whole only for a reader
signed in, D-159), and the stock pages' holders named in English."""

import uuid
from datetime import UTC, date, datetime

import httpx
import pytest

from autora.domains.newsroom.markets import edgar_13f
from autora.domains.newsroom.models import (
    CusipSymbol,
    PortfolioPosition,
    PortfolioQuarter,
    PortfolioStat,
    Source,
)
from tests.api.readers import sign_in
from tests.conftest import unique_company

Q2, Q1 = date(2026, 6, 30), date(2026, 3, 31)


@pytest.fixture
async def public(api):
    async with httpx.AsyncClient(transport=api._transport, base_url="http://test") as client:
        yield client


def _source(company_id, name, cik):
    return Source(
        id=uuid.uuid4(),
        company_id=company_id,
        name=f"SEC 13F：{name}",
        kind="rss",
        url=edgar_13f(cik),
        config={"title_prefix": name, "primary": True, "section": "holdings"},
    )


def _stat(source, company_id, **fields):
    positions = [
        {
            "cusip": f"C{i:08d}",
            "symbol": "AAPL" if i == 0 else f"T{i}",
            "issuer": "APPLE INC" if i == 0 else f"ISSUER {i}",
            "change": "increased" if i == 0 else "unchanged",
            "shares": 125 if i == 0 else 10,
            "previous_shares": 100 if i == 0 else 10,
            "value_usd": 1000 - i * 50,
            "weight": round((1000 - i * 50) / 8700, 6),
        }
        for i in range(12)
    ]
    holdings = [
        {"cusip": p["cusip"], "symbol": p["symbol"], "issuer": p["issuer"],
         "value_usd": p["value_usd"], "weight": p["weight"]}
        for p in positions[:10]
    ]  # fmt: skip
    return PortfolioStat(
        source_id=source.id,
        company_id=company_id,
        period=Q2,
        filed=date(2026, 8, 14),
        long_value_usd=8700,
        holdings=holdings,
        moves=[
            {
                "cusip": "C00000000",
                "symbol": "AAPL",
                "issuer": "APPLE INC",
                "change": "increased",
                "shares": 125,
                "previous_shares": 100,
                "value_change_usd": 200,
            },
        ],  # fmt: skip
        positions=positions,
        stretches=[
            {"start": "2025-09-30", "end": "2025-12-31", "growth": 1.02, "coverage": 1.0},
            {"start": "2025-12-31", "end": "2026-10-05", "growth": 1.1, "coverage": 0.95},
        ],
        computed_at=datetime(2026, 10, 6, tzinfo=UTC),
        **fields,
    )


@pytest.fixture
async def dashboard(committed):
    async with committed() as session:
        company = await unique_company(session)
        buffett = _source(company.id, "巴菲特（Berkshire Hathaway）", "0001067983")
        nvidia = _source(company.id, "輝達（NVIDIA）", "0001045810")
        unknown = _source(company.id, "某人", "0000000042")  # no profile: no card
        session.add_all([buffett, nvidia, unknown])
        await session.flush()
        session.add_all(
            [
                # NVIDIA first in the table, Buffett first on the page: the profiles' order
                _stat(nvidia, company.id, return_pct=None, pending=3),
                _stat(
                    buffett,
                    company.id,
                    return_pct=0.1385,
                    return_start=date(2025, 9, 30),
                    return_through=date(2026, 10, 5),
                    coverage=0.934,
                ),
                _stat(unknown, company.id),
            ]
        )
        for period, accession in ((Q2, "0001193125-26-352200"), (Q1, "0001193125-26-226661")):
            session.add(
                PortfolioQuarter(
                    company_id=company.id,
                    source_id=buffett.id,
                    period=period,
                    filed=date(2026, 8, 14) if period == Q2 else date(2026, 5, 15),
                    filings=[{"cik": "1067983", "accession": accession}],
                    total_value_usd=8700,
                )
            )
        await session.commit()
        return company.slug


async def test_the_cards_in_the_profiles_order_named_in_each_language(public, dashboard):
    answer = await public.get(
        "/api/public/holdings", params={"lang": "zh-TW", "company": dashboard}
    )
    assert answer.status_code == 200, answer.text
    assert answer.headers["cache-control"] == "public, max-age=600"
    zh = answer.json()
    assert [(c["slug"], c["name"], c["kind"], c["entity"]) for c in zh] == [
        ("buffett", "巴菲特", "person", "波克夏海瑟威"),
        ("nvidia", "輝達", "company", "輝達"),
    ]
    buffett, nvidia = zh
    assert (buffett["return_pct"], buffett["coverage"], buffett["pending"]) == (0.1385, 0.934, 0)
    assert (nvidia["return_pct"], nvidia["pending"]) == (None, 3), "整理中"
    assert [h["name"] for h in buffett["holdings"]][:2] == ["蘋果", "ISSUER 1"], "the site's name"
    assert len(buffett["holdings"]) == 5
    assert buffett["others_weight"] == pytest.approx(
        1 - sum(h["weight"] for h in buffett["holdings"])
    )
    [move] = buffett["moves"]
    assert (move["symbol"], move["change"], move["shares_change_pct"]) == (
        "AAPL",
        "increased",
        25.0,
    )

    en = (
        await public.get("/api/public/holdings", params={"lang": "en", "company": dashboard})
    ).json()
    assert [(c["name"], c["entity"]) for c in en] == [
        ("Warren Buffett", "Berkshire Hathaway"),
        ("NVIDIA", "NVIDIA"),
    ]
    assert en[0]["holdings"][0]["name"] == "Apple"


async def test_a_person_page_whole_only_for_a_reader_signed_in(public, dashboard, mailbox):
    path = "/api/public/holdings/people/buffett"
    params = {"lang": "zh-TW", "company": dashboard}
    stranger = await public.get(path, params=params)
    assert stranger.status_code == 200, stranger.text
    assert stranger.headers["cache-control"] == "private, no-store"
    page = stranger.json()
    assert (len(page["positions"]), page["positions_total"], page["locked"]) == (10, 12, True)
    assert page["positions"][0]["shares_change_pct"] == 25.0
    assert [s["growth"] for s in page["stretches"]] == [1.02, 1.1]
    assert [q["period"] for q in page["quarters"]] == ["2026-06-30", "2026-03-31"]
    assert page["quarters"][0]["filings"] == [
        "https://www.sec.gov/Archives/edgar/data/1067983/000119312526352200/"
        "0001193125-26-352200-index.htm"
    ]

    await sign_in(public, "holdings-reader@example.com")
    page = (await public.get(path, params=params)).json()
    assert (len(page["positions"]), page["locked"]) == (12, False)


async def test_no_such_person_or_company(public, dashboard):
    missing = await public.get(
        "/api/public/holdings/people/nobody", params={"lang": "zh-TW", "company": dashboard}
    )
    assert missing.status_code == 404
    no_company = await public.get("/api/public/holdings", params={"lang": "zh-TW", "company": "x"})
    assert no_company.status_code == 404


async def test_a_person_page_before_a_run_has_kept_its_table(public, committed):
    """HD-06: the runs can wait behind the worker's longer schedules; the page works the table
    out from the two latest quarters meanwhile, rather than saying nothing is held."""
    async with committed() as session:
        company = await unique_company(session)
        burry = _source(company.id, "麥可・貝瑞（Scion）", "0001649339")
        session.add(burry)
        await session.flush()
        for period, held in (
            (Q1, [("60855R100", "MOLINA HEALTHCARE INC", 100, 30_000)]),
            (Q2, [("60855R100", "MOLINA HEALTHCARE INC", 150, 45_000),
                  ("550021109", "LULULEMON ATHLETICA INC", 50, 10_000)]),
        ):  # fmt: skip
            quarter = PortfolioQuarter(
                company_id=company.id,
                source_id=burry.id,
                period=period,
                filed=period,
                filings=[{"cik": "1649339", "accession": f"0001649339-26-0000{period.month:02d}"}],
                total_value_usd=sum(v for *_, v in held),
            )
            session.add(quarter)
            await session.flush()
            session.add_all(
                PortfolioPosition(
                    quarter_id=quarter.id, cusip=cusip, issuer=issuer, title_of_class="COM",
                    kind="SH", amount=shares, value_usd=value,
                )
                for cusip, issuer, shares, value in held
            )  # fmt: skip
        session.add(CusipSymbol(cusip="60855R100", symbol="MOH", checked_at=datetime.now(UTC)))
        stat = _stat(burry, company.id)
        stat.positions, stat.stretches = [], []
        session.add(stat)
        await session.commit()
        slug = company.slug

    page = (
        await public.get(
            "/api/public/holdings/people/burry", params={"lang": "zh-TW", "company": slug}
        )
    ).json()
    assert [
        (p["symbol"], p["name"], p["change"], p["shares_change_pct"]) for p in page["positions"]
    ] == [
        ("MOH", "MOLINA HEALTHCARE INC", "increased", 50.0),
        (None, "LULULEMON ATHLETICA INC", "new", None),
    ]
    assert page["positions_total"] == 2
