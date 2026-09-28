"""D-096: 分析師評等 — Finnhub's counts as reported, TSMC through its ADR, asked twice a day."""

from datetime import UTC, datetime, timedelta

from autora.domains.newsroom.analysts import FINNHUB_RECOMMENDATION, AnalystRatings

NOW = datetime(2026, 9, 28, 2, tzinfo=UTC)
COUNTS = {"buy": 41, "hold": 3, "sell": 1, "strongSell": 0}
ROWS = [
    {"symbol": "NVDA", "period": "2026-08-01", "strongBuy": 23, **COUNTS},
    {"symbol": "NVDA", "period": "2026-09-01", "strongBuy": 24, **COUNTS},
]


async def test_the_latest_month_and_the_one_before_counted():
    asked: list[tuple[str, dict]] = []

    async def finnhub(url: str, params: dict) -> object:
        asked.append((url, params))
        return ROWS

    ratings = AnalystRatings(finnhub, clock=lambda: NOW)
    nvda = await ratings.ratings("nvda")
    assert nvda is not None and nvda.symbol == "NVDA" and nvda.via is None
    assert str(nvda.latest.period) == "2026-09-01" and nvda.latest.total == 69
    assert nvda.previous is not None and nvda.previous.strong_buy == 23
    assert asked == [(FINNHUB_RECOMMENDATION, {"symbol": "NVDA"})]
    await ratings.ratings("NVDA")
    assert len(asked) == 1  # kept for twelve hours


async def test_tsmc_through_its_adr_and_the_rest_of_taiwan_has_none():
    asked: list[str] = []

    async def finnhub(url: str, params: dict) -> object:
        asked.append(params["symbol"])
        return ROWS

    ratings = AnalystRatings(finnhub, clock=lambda: NOW)
    tsmc = await ratings.ratings("2330")
    assert tsmc is not None and (tsmc.symbol, tsmc.via) == ("2330", "TSM")
    assert await ratings.ratings("2317") is None
    assert asked == ["TSM"]
    assert await AnalystRatings(None).ratings("NVDA") is None  # no key, offline


async def test_none_rated_and_a_failure_keeps_the_last_answer():
    clock = [NOW]
    answers: list[object] = [ROWS, RuntimeError("HTTP 429")]

    async def finnhub(url: str, params: dict) -> object:
        answer = answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer

    ratings = AnalystRatings(finnhub, clock=lambda: clock[0])
    assert (await ratings.ratings("NVDA")).latest.total == 69
    clock[0] = NOW + timedelta(hours=13)
    assert (await ratings.ratings("NVDA")).latest.total == 69  # Finnhub failed: the last stands

    async def empty(url: str, params: dict) -> object:
        return []

    assert await AnalystRatings(empty).ratings("ZZZZ") is None
