"""D-061: any listed Taiwan or US stock — found by search, with a page, a chart and a quote."""

from datetime import date
from decimal import Decimal

import httpx
import pytest
from sqlalchemy import delete, select

from autora.domains.newsroom import price_history, securities
from autora.domains.newsroom.models import PriceBar, TrackedSecurity


@pytest.fixture
async def public(api, db_session):
    from autora_api.routers.public import market_board

    class NoQuotes:
        async def quotes(self):
            return []

    await db_session.execute(delete(PriceBar).where(PriceBar.symbol.in_(("6488", "PLTR"))))
    await securities.store(
        db_session,
        [
            securities.Listed("tw", "6488", "環球晶", None, "TPEx", "stock"),
            securities.Listed("us", "PLTR", "PALANTIR TECHNOLOGIES INC-A", None, "XNAS", "stock"),
        ],
    )
    api._transport.app.dependency_overrides[market_board] = lambda: NoQuotes()
    async with httpx.AsyncClient(transport=api._transport, base_url="http://test") as client:
        yield client


async def test_a_listed_stock_is_found_by_code_or_name(public):
    found = (await public.get("/api/public/securities", params={"q": "環球"})).json()
    assert [(s["symbol"], s["exchange"]) for s in found] == [("6488", "TPEx")]
    assert (await public.get("/api/public/securities", params={"q": "pltr"})).json()[0]["name"] == (
        "PALANTIR TECHNOLOGIES INC-A"
    )


async def test_any_listed_stock_has_a_page_without_a_13f_section(public, db_session):
    page = await public.get("/api/public/stocks/6488", params={"lang": "zh-TW"})
    assert page.status_code == 200, page.text
    body = page.json()
    assert (body["name"], body["market"], body["tracks_13f"], body["quote"]) == (
        "環球晶", "tw", False, None
    )  # fmt: skip
    assert body["exchange"] == "TPEx"  # its code reads 6488.TWO
    assert (
        await public.get("/api/public/stocks/9999", params={"lang": "zh-TW"})
    ).status_code == 404


async def test_a_new_taiwan_stock_s_chart_is_being_prepared_and_the_stock_tracked(
    public, db_session
):
    history = (await public.get("/api/public/stocks/6488/history")).json()
    assert history["bars"] == [] and history["preparing"] is True
    tracked = await db_session.scalar(
        select(TrackedSecurity).where(TrackedSecurity.symbol == "6488")
    )
    assert tracked is not None


async def test_once_it_has_days_its_quote_is_the_last_close(public, db_session):
    bars = [
        price_history.Bar(date(2026, 9, 23), Decimal("990"), Decimal("995"), Decimal("980"),
                          Decimal("990"), 1000),
        price_history.Bar(date(2026, 9, 24), Decimal("990"), Decimal("1000"), Decimal("985"),
                          Decimal("999"), 2000),
    ]  # fmt: skip
    await price_history._store(db_session, "tw", "6488", bars, source="TPEx")
    quote = (await public.get("/api/public/stocks/6488", params={"lang": "zh-TW"})).json()["quote"]
    assert (quote["value"], quote["previous_close"], quote["source"]) == (999.0, 990.0, "TPEx")
    listed = (await public.get("/api/public/quotes", params={"keys": "tw:6488,us:PLTR,x:y"})).json()
    assert [q["key"] for q in listed] == ["tw:6488"]  # PLTR has no days yet: left out
    history = (await public.get("/api/public/stocks/6488/history")).json()
    assert len(history["bars"]) == 2 and history["preparing"] is False


async def test_the_strip_s_figures_are_found_too(public):
    """D-189: 台指期 and the strip's other figures by symbol, name or what people call them."""
    for q in ("TXF1", "txf", "台指期", "台指", "期貨"):
        found = (await public.get("/api/public/securities", params={"q": q})).json()
        assert {"symbol": "TXF1", "market": "market", "name": "台指期", "name_en": "TAIEX futures",
                "exchange": "TAIFEX", "kind": "future"} in found, q  # fmt: skip
    assert (await public.get("/api/public/securities", params={"q": "大盤"})).json()[0][
        "symbol"
    ] == ("TAIEX")
    coins = (await public.get("/api/public/securities", params={"q": "比特幣"})).json()
    assert coins[0]["symbol"] == "BTC" and coins[0]["kind"] == "crypto"
