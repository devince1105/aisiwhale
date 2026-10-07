"""HD-12: Taiwan's three institutional investors, from TWSE's and TPEx's own daily documents —
excerpts of 2026-10-06's four (``fixtures/tw``) and of a Sunday's — read a few at a time, a stock
page's days and sums, and the day's ranking without ETFs."""

import json
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select

from autora.domains.newsroom import tw_flows
from autora.domains.newsroom.models import TwFlow, TwFlowRead
from autora.domains.newsroom.tw_flows import (
    for_stock,
    parse_tpex_flows,
    parse_tpex_ratios,
    parse_twse_flows,
    parse_twse_ratios,
    ranking,
    refresh_flows,
)

TW = Path(__file__).parent / "fixtures" / "tw"
NOW = datetime(2026, 10, 7, 9, 0, tzinfo=UTC)
DAY = date(2026, 10, 6)


def load(name: str) -> dict:
    return json.loads((TW / name).read_text("utf-8"))


def test_twse_s_flows_and_ratios():
    flows = {f.symbol: f for f in parse_twse_flows(load("twse-t86-20261006.json"))}
    # TSMC: foreign investors sold 1,672,231 shares, trusts and dealers bought; together −1,121,670
    tsmc = flows["2330"]
    assert (tsmc.name, tsmc.foreign, tsmc.trust, tsmc.dealer, tsmc.total) == (
        "台積電",
        -1_672_231,
        154_586,
        395_975,
        -1_121_670,
    )
    assert tsmc.foreign + tsmc.trust + tsmc.dealer == tsmc.total
    ratios = {r.symbol: r for r in parse_twse_ratios(load("twse-qfiis-20261006.json"))}
    assert (ratios["2330"].issued, ratios["2330"].held, ratios["2330"].pct) == (
        25_932_370_067,
        17_945_787_521,
        Decimal("69.2"),
    )


def test_tpex_s_flows_and_ratios():
    flows = {f.symbol: f for f in parse_tpex_flows(load("tpex-daily-20261006.json"))}
    gw = flows["6488"]  # 環球晶
    assert (gw.foreign, gw.trust, gw.dealer, gw.total) == (-518_347, 106_000, 103_667, -308_680)
    ratios = {r.symbol: r for r in parse_tpex_ratios(load("tpex-qfii-20261006.json"))}
    assert ratios["6488"].pct == Decimal("36.25") and ratios["6488"].issued == 478_113_725


def test_a_day_with_nothing_is_none():
    assert parse_twse_flows(load("twse-t86-holiday.json")) is None
    assert parse_tpex_flows(load("tpex-daily-holiday.json")) is None


def exchanges(asked: list | None = None):
    """TWSE and TPEx as the fixtures: 2026-10-06 has its four documents, any other day none (a
    Sunday's answers)."""
    pages = {
        tw_flows.TWSE_FLOWS: "twse-t86-20261006.json",
        tw_flows.TWSE_RATIOS: "twse-qfiis-20261006.json",
        tw_flows.TPEX_FLOWS: "tpex-daily-20261006.json",
        tw_flows.TPEX_RATIOS: "tpex-qfii-20261006.json",
    }
    empty = {
        tw_flows.TWSE_FLOWS: "twse-t86-holiday.json",
        tw_flows.TWSE_RATIOS: "twse-t86-holiday.json",
        tw_flows.TPEX_FLOWS: "tpex-daily-holiday.json",
        tw_flows.TPEX_RATIOS: "tpex-daily-holiday.json",
    }

    async def get(url: str, params: dict) -> dict:
        if asked is not None:
            asked.append((url, params["date"]))
        shown = params["date"].replace("/", "")
        return load(pages[url] if shown == "20261006" else empty[url])

    return get


async def test_the_latest_day_first_four_documents_and_a_holiday_kept(db_session):
    asked: list = []

    read = await refresh_flows(
        db_session, exchanges(asked), today=date(2026, 10, 7), limit=8, pause=0, now=NOW
    )

    # 10/07's (today) are not out: asked, not kept; then 10/06's four
    assert asked[:4] == [
        (tw_flows.TWSE_FLOWS, "20261007"),
        (tw_flows.TPEX_FLOWS, "2026/10/07"),
        (tw_flows.TWSE_RATIOS, "20261007"),
        (tw_flows.TPEX_RATIOS, "2026/10/07"),
    ]
    assert read == 4
    reads = {(r.day, r.source): r.rows for r in (await db_session.scalars(select(TwFlowRead)))}
    assert reads == {
        (DAY, "twse_flows"): 5,
        (DAY, "tpex_flows"): 3,
        (DAY, "twse_ratios"): 5,
        (DAY, "tpex_ratios"): 2,
    }
    tsmc = await db_session.get(TwFlow, (DAY, "2330"))
    assert (tsmc.exchange, tsmc.total_net, tsmc.foreign_ratio) == (
        "TWSE",
        -1_121_670,
        Decimal("69.20"),
    )
    gw = await db_session.get(TwFlow, (DAY, "6488"))
    assert (gw.exchange, gw.trust_net, gw.foreign_ratio) == ("TPEx", 106_000, Decimal("36.25"))

    # the next run: the day before is a holiday (here, every other day is), kept as none
    asked.clear()
    await refresh_flows(
        db_session, exchanges(asked), today=date(2026, 10, 7), limit=6, pause=0, now=NOW
    )
    reads = {(r.day, r.source): r.rows for r in (await db_session.scalars(select(TwFlowRead)))}
    assert reads[(date(2026, 10, 5), "twse_flows")] == 0
    assert (date(2026, 10, 7), "twse_flows") not in reads  # today's: asked again next time
    assert asked[0] == (tw_flows.TWSE_FLOWS, "20261007")


async def test_an_exchange_s_bad_hour_ends_the_run(db_session):
    async def down(url: str, params: dict) -> dict:
        raise RuntimeError("503")

    assert await refresh_flows(db_session, down, today=date(2026, 10, 7), pause=0, now=NOW) == 0
    assert (await db_session.scalars(select(TwFlowRead))).all() == []


def flow(day, symbol, foreign, trust=0, dealer=0, ratio=None, exchange="TWSE"):
    return TwFlow(
        day=day,
        symbol=symbol,
        exchange=exchange,
        name=f"{symbol} 公司",
        foreign_net=foreign,
        trust_net=trust,
        dealer_net=dealer,
        total_net=foreign + trust + dealer,
        foreign_ratio=ratio,
        read_at=NOW,
    )


async def test_a_stock_s_days_and_sums(db_session):
    days = [date(2026, 9, d) for d in range(1, 31) if date(2026, 9, d).weekday() < 5][-21:]
    db_session.add_all(
        flow(d, "2330", 1000 * (n + 1), trust=-100, ratio=Decimal("69.00") + Decimal(n) / 100)
        for n, d in enumerate(days)
    )
    await db_session.flush()

    page = await for_stock(db_session, "2330")

    assert [d.day for d in page.days] == list(reversed(days))[:10]
    assert page.days[0].foreign == 21_000 and page.days[0].total == 20_900
    five, twenty = page.sums
    assert (five.days, five.foreign, five.trust) == (5, 1000 * (21 + 20 + 19 + 18 + 17), -500)
    assert (twenty.days, twenty.foreign) == (20, 1000 * sum(range(2, 22)))
    # the ratio now, and against twenty trading days back
    assert (page.foreign_ratio, page.foreign_ratio_day) == (69.2, days[-1])
    assert page.foreign_ratio_change == 0.19
    assert await for_stock(db_session, "9999") is None
    # fewer than twenty days kept: no change over twenty days to give
    db_session.add_all(flow(d, "2454", 1000, ratio=Decimal("55.00")) for d in days[-5:])
    await db_session.flush()
    short = await for_stock(db_session, "2454")
    assert (short.foreign_ratio, short.foreign_ratio_change, len(short.sums)) == (55.0, None, 1)


async def test_the_day_s_ranking_is_of_companies(db_session, monkeypatch):
    monkeypatch.setattr(tw_flows, "MIN_DAY_ROWS", 1)
    db_session.add_all(
        [
            flow(DAY, "2330", -1_672_231, ratio=Decimal("69.20")),
            flow(DAY, "2317", -19_982_641),
            flow(DAY, "2454", 3_000_000),
            flow(DAY, "6488", 500_000, trust=106_000, exchange="TPEx"),
            flow(DAY, "00981A", 19_367_911),  # an ETF: left out
            flow(date(2026, 10, 5), "2330", 7),
        ]
    )
    await db_session.flush()

    bought = await ranking(db_session)
    sold = await ranking(db_session, side="sell")
    trusts = await ranking(db_session, group="trust")

    assert (bought.day, bought.days) == (DAY, [DAY, date(2026, 10, 5)])
    assert [(r.rank, r.symbol, r.net) for r in bought.rows] == [
        (1, "2454", 3_000_000),
        (2, "6488", 500_000),
    ]
    assert [r.symbol for r in sold.rows] == ["2317", "2330"]
    assert sold.rows[1].foreign_ratio == 69.2
    assert [r.symbol for r in trusts.rows] == ["6488"]
    assert (await ranking(db_session, day=date(2026, 10, 5))).rows[0].symbol == "2330"
    assert (await ranking(db_session, day=date(2020, 1, 2))).day == DAY  # not offered: the latest
