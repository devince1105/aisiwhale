"""D-069: the 外匯 tab's reference rates — Bank of Taiwan's nineteen currencies, in New Taiwan
dollars for one unit, asked of the provider once per update."""

from datetime import UTC, datetime, timedelta

import httpx

from autora.domains.newsroom import fx_rates, markets
from autora.domains.newsroom.fx_rates import FxBoard, board_from

UPDATED = datetime(2026, 9, 27, 0, 2, 31, tzinfo=UTC)
NEXT = datetime(2026, 9, 28, 0, 17, 1, tzinfo=UTC)


def answer(**rates: float) -> dict:
    return {
        "result": "success",
        "base_code": "TWD",
        "time_last_update_unix": int(UPDATED.timestamp()),
        "time_next_update_unix": int(NEXT.timestamp()),
        "rates": {"TWD": 1, "USD": 0.031486, "JPY": 4.953, "EUR": 0.027628, "XAU": 0.00001} | rates,
    }


def test_rates_per_one_unit_in_the_bank_s_order_and_names():
    board = board_from(answer(), "zh-TW")
    assert board is not None and board.as_of == UPDATED
    assert [(r.code, r.name) for r in board.rates] == [
        ("USD", "美金"),
        ("JPY", "日圓"),
        ("EUR", "歐元"),
    ]
    usd = board.rates[0]
    assert round(usd.twd, 2) == 31.76  # one US dollar, in New Taiwan dollars
    assert board.bank_url.startswith("https://rate.bot.com.tw")
    assert (
        board.source == "ExchangeRate-API"
        and board.source_url == "https://www.exchangerate-api.com"
    )
    assert board_from(answer(), "en").rates[0].name == "US dollar"
    # a currency the bank does not post (gold here) is left out; a zero is not divided by
    assert "XAU" not in {r.code for r in board.rates}
    assert "JPY" not in {r.code for r in board_from(answer(JPY=0), "zh-TW").rates}
    assert board_from({"result": "error", "error-type": "unsupported-code"}, "zh-TW") is None


def test_the_currencies_are_the_ones_the_searches_cover():
    assert markets.FX_CURRENCIES == tuple(c for c, _, _ in fx_rates.CURRENCIES)
    assert len(markets.FX_CURRENCIES) == 19


async def test_asked_once_per_update_and_the_last_answer_stands_when_it_fails():
    now = [UPDATED + timedelta(hours=1)]
    asked: list[str] = []
    fail = [False]

    async def get(url: str) -> dict:
        asked.append(url)
        if fail[0]:
            raise httpx.ConnectError("down")
        return answer()

    board = FxBoard(get, clock=lambda: now[0])
    assert (await board.board("zh-TW")).rates[0].code == "USD"
    await board.board("en")
    assert asked == [fx_rates.ENDPOINT], "one ask serves every reader until the next update"
    now[0] = NEXT + timedelta(minutes=6)
    fail[0] = True
    assert (await board.board("zh-TW")) is not None, "the last good answer stands"
    assert len(asked) == 2
    await board.board("zh-TW")
    assert len(asked) == 2, "and is not asked again for an hour"


async def test_offline_there_is_no_board_and_nobody_is_asked():
    assert await FxBoard(None).board("zh-TW") is None
