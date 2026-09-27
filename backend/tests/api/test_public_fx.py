"""D-069: the 外匯 tab's reference rates, as the API gives them."""

import httpx
import pytest

from autora.domains.newsroom.fx_rates import FxBoard
from tests.newsroom.test_fx_rates import answer


@pytest.fixture
async def public(api):
    async with httpx.AsyncClient(transport=api._transport, base_url="http://test") as client:
        yield client


async def test_the_api(public):
    from autora_api.routers.public import fx_board

    async def get(url: str) -> dict:
        return answer()

    public._transport.app.dependency_overrides[fx_board] = lambda: FxBoard(get)
    try:
        body = (await public.get("/api/public/fx", params={"lang": "zh-TW"})).json()
        assert [r["code"] for r in body["rates"]] == ["USD", "JPY", "EUR"]
        assert body["bank_url"].startswith("https://rate.bot.com.tw")
        public._transport.app.dependency_overrides[fx_board] = lambda: FxBoard(None)
        assert (await public.get("/api/public/fx", params={"lang": "zh-TW"})).json() is None
    finally:
        public._transport.app.dependency_overrides.pop(fx_board)


async def test_the_gold_api(public):
    from autora.domains.newsroom.gold import GoldBoard
    from autora_api.routers.public import gold_board
    from tests.newsroom.test_gold import ROWS

    async def get(url: str, params: dict) -> list[dict]:
        return ROWS

    public._transport.app.dependency_overrides[gold_board] = lambda: GoldBoard(get, FxBoard(None))
    try:
        body = (await public.get("/api/public/gold", params={"lang": "zh-TW"})).json()
        assert (body["usd_per_oz"], len(body["bars"]), body["twd_per_gram"]) == (4805, 3, None)
        public._transport.app.dependency_overrides[gold_board] = lambda: GoldBoard(
            None, FxBoard(None)
        )
        assert (await public.get("/api/public/gold", params={"lang": "zh-TW"})).json() is None
    finally:
        public._transport.app.dependency_overrides.pop(gold_board)
