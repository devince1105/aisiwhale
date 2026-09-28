"""D-091: 新聞情緒 — the week's headlines about the strip's stocks, their tone counted."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select

from autora.domains.newsroom.holdings import STOCKS
from autora.domains.newsroom.models import StockHeadline
from autora.domains.newsroom.sentiment import (
    CNA_FINANCE,
    FINNHUB_NEWS,
    YAHOO_TW,
    Reading,
    from_feed,
    from_finnhub,
    refresh,
    stock_sentiment,
)

NOW = datetime(2026, 9, 28, 2, tzinfo=UTC)
TSMC, NVDA = STOCKS["2330"], STOCKS["NVDA"]


def rss(*items: tuple[str, str, str]) -> bytes:
    body = "".join(
        f"<item><title>{t}</title><link>{u}</link><pubDate>{d}</pubDate></item>"
        for t, u, d in items
    )
    return f"<rss><channel><title>x</title>{body}</channel></rss>".encode()


YAHOO = rss(
    (
        "台積電A16預計2026年第4季量產",
        "https://tw.stock.yahoo.com/n/1",
        "Mon, 28 Sep 2026 01:00:00 GMT",
    ),
    ("外資賣超台股338億", "https://tw.stock.yahoo.com/n/2", "Mon, 28 Sep 2026 01:00:00 GMT"),
    ("台積電遭調降評等", "https://tw.stock.yahoo.com/n/3", "Sun, 27 Sep 2026 01:00:00 GMT"),
)
CNA = rss(("國發會攜手台積電赴矽谷攬才", "https://cna.com.tw/n/4", "Sun, 27 Sep 2026 03:00:00 GMT"))


def test_a_word_other_than_the_three_is_neutral():
    assert Reading(index=1, sentiment="Mixed", reason_zh="", reason_en="").sentiment == "neutral"
    assert (
        Reading(index=1, sentiment=" Positive ", reason_zh="", reason_en="").sentiment == "positive"
    )


def test_only_a_headline_that_names_the_stock():
    assert [f.url for f in from_feed(TSMC, YAHOO, "Yahoo股市")] == [
        "https://tw.stock.yahoo.com/n/1",
        "https://tw.stock.yahoo.com/n/3",
    ]
    rows = [
        {
            "headline": "Nvidia unveils Rubin",
            "url": "https://x/1",
            "datetime": 1790000000,
            "source": "Reuters",
        },
        {
            "headline": "Is Costco overdue for a rally?",
            "url": "https://x/2",
            "datetime": 1790000000,
        },
        {"headline": "NVIDIA and TSMC", "url": "https://x/3", "datetime": 1790000000},
        {"headline": "NVDAX fund", "url": "https://x/4", "datetime": 1790000000},
    ]
    assert [f.url for f in from_finnhub(NVDA, rows)] == ["https://x/1", "https://x/3"]
    assert from_feed(TSMC, b"not xml", "x") == []


async def test_new_headlines_read_once_and_counted(db_session):
    await db_session.execute(
        delete(StockHeadline).where(StockHeadline.stock_key.in_(["tw:2330", "us:NVDA"]))
    )
    asked: list[str] = []
    read: list[list[str]] = []

    async def feed(url: str, params: dict) -> bytes:
        asked.append(url)
        return CNA if url == CNA_FINANCE else YAHOO

    async def finnhub(url: str, params: dict) -> object:
        assert url == FINNHUB_NEWS and params["symbol"] == "NVDA"
        return [
            {
                "headline": "Nvidia beats estimates",
                "url": "https://x/n1",
                "datetime": int((NOW - timedelta(hours=3)).timestamp()),
                "source": "Reuters",
            }
        ]

    async def classify(company: str, titles: list[str]) -> list[Reading]:
        read.append(titles)
        tone = {"遭調降": "negative", "攬才": "neutral"}
        return [
            Reading(
                index=i,
                sentiment=next((v for k, v in tone.items() if k in t), "positive"),
                reason_zh="理由",
                reason_en="why",
            )
            for i, t in enumerate(titles, 1)
        ]

    stocks = (TSMC, NVDA)
    assert (
        await refresh(
            db_session, classify=classify, finnhub=finnhub, feed=feed, now=NOW, stocks=stocks
        )
        == 4
    )
    assert (
        await refresh(
            db_session, classify=classify, finnhub=finnhub, feed=feed, now=NOW, stocks=stocks
        )
        == 0
    )
    assert len(read) == 2, "each stock read once: the second run finds nothing new"
    assert asked.count(YAHOO_TW) == 2 and asked.count(CNA_FINANCE) == 2  # Yahoo for 2330 only

    tsmc = await stock_sentiment(db_session, TSMC, "zh-TW", now=NOW)
    assert (tsmc.positive, tsmc.neutral, tsmc.negative, tsmc.total) == (1, 1, 1, 3)
    assert tsmc.heat is None  # no four weeks to compare with yet
    assert [h.url for h in tsmc.headlines] == [
        "https://tw.stock.yahoo.com/n/1",
        "https://cna.com.tw/n/4",
        "https://tw.stock.yahoo.com/n/3",
    ]  # newest first
    assert tsmc.headlines[0].reason == "理由"
    assert (await stock_sentiment(db_session, NVDA, "en", now=NOW)).headlines[0].reason == "why"
    await db_session.execute(
        delete(StockHeadline).where(StockHeadline.stock_key.in_(["tw:2330", "us:NVDA"]))
    )


async def test_a_failed_reading_is_tried_again_and_heat_compares_four_weeks(db_session):
    await db_session.execute(delete(StockHeadline).where(StockHeadline.stock_key == "tw:2330"))

    async def feed(url: str, params: dict) -> bytes:
        return YAHOO if url == YAHOO_TW else b""

    async def broken(company: str, titles: list[str]) -> list[Reading]:
        raise ValueError("no parse")

    assert (
        await refresh(db_session, classify=broken, finnhub=None, feed=feed, now=NOW, stocks=(TSMC,))
        == 0
    )
    unread = (
        await db_session.scalars(select(StockHeadline).where(StockHeadline.stock_key == "tw:2330"))
    ).all()
    assert len(unread) == 2 and all(h.sentiment is None for h in unread)

    # four weeks before: two headlines a week on average (eight), this week's two read now
    for week in range(1, 5):
        for n in range(2):
            db_session.add(
                StockHeadline(
                    stock_key="tw:2330",
                    url=f"https://old/{week}/{n}",
                    title="台積電",
                    source="Yahoo股市",
                    published_at=NOW - timedelta(days=7 * week + 7),
                    sentiment="neutral",
                )  # fmt: skip
            )
    await db_session.flush()

    async def fine(company: str, titles: list[str]) -> list[Reading]:
        return [
            Reading(index=i, sentiment="positive", reason_zh="好", reason_en="good")
            for i in range(1, len(titles) + 1)
        ]

    assert (
        await refresh(db_session, classify=fine, finnhub=None, feed=feed, now=NOW, stocks=(TSMC,))
        == 2
    )
    tsmc = await stock_sentiment(db_session, TSMC, "zh-TW", now=NOW)
    assert (tsmc.positive, tsmc.total, tsmc.heat) == (2, 2, 1.0)  # as usual
    await db_session.execute(delete(StockHeadline).where(StockHeadline.stock_key == "tw:2330"))


async def test_one_story_carried_by_two_sources_is_one_headline(db_session):
    await db_session.execute(delete(StockHeadline).where(StockHeadline.stock_key == "tw:2330"))
    # 中央社's own story, carried by Yahoo at its own address, a space and a mark apart
    copy = rss(
        (
            "台積電 A16預計2026年第4季量產！",
            "https://cna.com.tw/n/9",
            "Mon, 28 Sep 2026 00:30:00 GMT",
        )
    )

    async def feed(url: str, params: dict) -> bytes:
        return copy if url == CNA_FINANCE else YAHOO

    async def fine(company: str, titles: list[str]) -> list[Reading]:
        return [
            Reading(index=i, sentiment="positive", reason_zh="", reason_en="")
            for i in range(1, len(titles) + 1)
        ]

    for _ in range(2):  # and not again the next time either
        await refresh(db_session, classify=fine, finnhub=None, feed=feed, now=NOW, stocks=(TSMC,))
    tsmc = await stock_sentiment(db_session, TSMC, "zh-TW", now=NOW)
    assert tsmc.total == 2
    assert [h.url for h in tsmc.headlines] == [
        "https://tw.stock.yahoo.com/n/1",
        "https://tw.stock.yahoo.com/n/3",
    ]
    await db_session.execute(delete(StockHeadline).where(StockHeadline.stock_key == "tw:2330"))
