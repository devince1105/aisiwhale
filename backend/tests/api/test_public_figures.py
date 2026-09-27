"""D-070–D-072 through the API: gold, a figure's chart, a currency found and quoted."""

import httpx
import pytest

from autora.domains.newsroom.figures import FredHistory
from autora.domains.newsroom.forex import TiingoFx
from tests.newsroom.test_forex import tiingo


@pytest.fixture
async def public(api):
    async with httpx.AsyncClient(transport=api._transport, base_url="http://test") as client:
        yield client


async def test_gold_figures_and_currencies(public):
    from autora_api.routers.public import forex_cache, fred_history

    app = public._transport.app
    forex = TiingoFx(tiingo([]))
    app.dependency_overrides[forex_cache] = lambda: forex
    app.dependency_overrides[fred_history] = lambda: FredHistory(None)
    try:
        gold = (await public.get("/api/public/gold", params={"lang": "zh-TW"})).json()
        assert (gold["usd_per_oz"], len(gold["bars"])) == (4284.91, 2)
        yen = (await public.get("/api/public/figures/jpytwd")).json()
        assert yen["source"] == "Tiingo" and len(yen["bars"]) == 2
        assert (await public.get("/api/public/figures/wti")).json() is None  # FRED offline
        assert (await public.get("/api/public/figures/BAD!")).status_code == 422
        # a currency is found by its name, and quoted once it is on a list
        found = (await public.get("/api/public/securities", params={"q": "日圓"})).json()
        assert found[0] == {
            "symbol": "JPYTWD",
            "market": "market",
            "name": "日圓",
            "name_en": "Japanese yen",
            "exchange": "Tiingo",
            "kind": "fx",
        }
        quoted = (await public.get("/api/public/quotes", params={"keys": "eurtwd,xau"})).json()
        assert [q["key"] for q in quoted] == ["eurtwd", "xau"]
        app.dependency_overrides[forex_cache] = lambda: TiingoFx(None)
        assert (await public.get("/api/public/gold", params={"lang": "zh-TW"})).json() is None
    finally:
        app.dependency_overrides.pop(forex_cache)
        app.dependency_overrides.pop(fred_history)


async def test_a_grain_is_found_quoted_and_charted_by_the_month(public):
    """D-080 through the API."""
    from autora_api.routers.public import forex_cache, fred_history

    async def fred(series: str) -> list[dict]:
        return [
            {"date": "2026-06-01", "value": "195.78"},
            {"date": "2026-07-01", "value": "213.19"},
        ]

    app = public._transport.app
    app.dependency_overrides[forex_cache] = lambda: TiingoFx(None)
    app.dependency_overrides[fred_history] = lambda: FredHistory(fred)
    try:
        found = (await public.get("/api/public/securities", params={"q": "玉米"})).json()
        assert found[0]["symbol"] == "MAIZE" and found[0]["kind"] == "commodity"
        [quote] = (await public.get("/api/public/quotes", params={"keys": "maize"})).json()
        assert (quote["value"], quote["basis"], quote["change_pct"]) == (213.19, "month", 8.89)
        chart = (await public.get("/api/public/figures/maize")).json()
        assert chart["interval"] == "month" and len(chart["bars"]) == 2
    finally:
        app.dependency_overrides.pop(forex_cache)
        app.dependency_overrides.pop(fred_history)
