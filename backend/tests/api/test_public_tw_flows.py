"""HD-12: Taiwan's three institutional investors on the public API — a trading day's ranking, the
same for every reader, and a Taiwan stock page's days of them (a US stock's page has none)."""

from datetime import UTC, date, datetime
from decimal import Decimal

import httpx
import pytest

from autora.domains.newsroom import tw_flows
from autora.domains.newsroom.models import TwFlow

DAY = date(2026, 10, 6)
NOW = datetime(2026, 10, 7, 9, 0, tzinfo=UTC)


@pytest.fixture
async def public(api):
    from autora_api.routers.public import market_board

    class NoQuotes:
        async def quotes(self):
            return []

    api._transport.app.dependency_overrides[market_board] = lambda: NoQuotes()
    async with httpx.AsyncClient(transport=api._transport, base_url="http://test") as client:
        yield client
    api._transport.app.dependency_overrides.pop(market_board)


@pytest.fixture
async def flows(db_session, monkeypatch):
    monkeypatch.setattr(tw_flows, "MIN_DAY_ROWS", 1)
    db_session.add_all(
        [
            TwFlow(
                day=DAY,
                symbol="2330",
                exchange="TWSE",
                name="台積電",
                foreign_net=-1_672_231,
                trust_net=154_586,
                dealer_net=395_975,
                total_net=-1_121_670,
                foreign_ratio=Decimal("69.20"),
                read_at=NOW,
            ),
            TwFlow(
                day=DAY,
                symbol="2454",
                exchange="TWSE",
                name="聯發科",
                foreign_net=3_000_000,
                trust_net=0,
                dealer_net=0,
                total_net=3_000_000,
                read_at=NOW,
            ),
        ]
    )
    await db_session.flush()


async def test_the_day_s_ranking(public, flows):
    answer = await public.get("/api/public/tw-flows")

    assert answer.status_code == 200, answer.text
    assert answer.headers["cache-control"] == "public, max-age=600"
    body = answer.json()
    assert (body["day"], body["group"], body["side"]) == ("2026-10-06", "foreign", "buy")
    assert [(r["rank"], r["symbol"], r["net"]) for r in body["rows"]] == [(1, "2454", 3_000_000)]
    sold = (await public.get("/api/public/tw-flows", params={"side": "sell"})).json()
    assert [(r["symbol"], r["foreign_ratio"]) for r in sold["rows"]] == [("2330", 69.2)]
    assert (await public.get("/api/public/tw-flows", params={"group": "x"})).status_code == 422


async def test_a_taiwan_stock_page_has_its_days(public, flows):
    page = (await public.get("/api/public/stocks/2330", params={"lang": "zh-TW"})).json()

    institutional = page["institutional"]
    assert institutional["exchange"] == "TWSE" and institutional["foreign_ratio"] == 69.2
    assert institutional["days"][0] == {
        "day": "2026-10-06",
        "foreign": -1_672_231,
        "trust": 154_586,
        "dealer": 395_975,
        "total": -1_121_670,
        "foreign_ratio": 69.2,
    }
    us = (await public.get("/api/public/stocks/AAPL", params={"lang": "zh-TW"})).json()
    assert us["institutional"] is None
