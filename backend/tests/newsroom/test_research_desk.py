"""D-256: the research desk's rules (``research.py``), its backtests (``backtest.py``) and the
price record (``snapshot.py``) — everything that runs without a database.

The bars here are made up for the tests (a trend with cycles); no product data is.
"""

import math
from datetime import date, timedelta

import pytest

from autora.domains.newsroom import backtest, research, snapshot
from autora.domains.newsroom.articles import Block, LanguageVersion
from autora.domains.newsroom.backtest import Bar


def bars(n: int, *, start: date = date(2020, 1, 2), volume: bool = True) -> list[Bar]:
    """A rising price with cycles and the odd volume spike: every rule trades on it."""
    out, day = [], start
    for i in range(n):
        c = 100 * (1 + 0.0008 * i) * (1 + 0.12 * math.sin(i / 17)) * (1 + 0.02 * math.sin(i / 3))
        o = c * (1 - 0.004 * math.sin(i / 5))
        out.append(
            Bar(
                day,
                o,
                max(o, c) * 1.01,
                min(o, c) * 0.99,
                c,
                (3000 if i % 19 == 0 else 1000) if volume else 0,
            )
        )
        day += timedelta(days=1 if day.weekday() < 4 else 3)
    return out


# --- what the editor-in-chief ranks by -----------------------------------------------------------


def test_a_story_is_tagged_with_the_companies_and_events_it_names():
    tags = research.tags_of("台積電第三季營收創新高，輝達 GPU 訂單帶動 CoWoS 擴產")
    assert [s.symbol for s in tags.stocks][:2] == ["2330", "NVDA"], "Taiwan's first"
    assert {"earnings", "orders_capex"} <= set(tags.events)
    assert research.tags_of("聯準會維持利率不變").stocks == ()
    assert research.tags_of("Micron orders surge; regulators probe").events == (
        "orders_capex",
        "policy",
        "legal",
    )
    assert research.tags_of("Border bank reopens").events == (), "whole words, not parts"


def test_research_value_ranks_a_named_company_and_an_event_above_score_alone():
    plain = research.tags_of("全球股市週線收紅")
    named = research.tags_of("美光財報優於預期")
    assert research.research_value(0.9, plain) == 0.45
    assert research.research_value(0.5, named) == 0.75
    assert research.research_value(0.5, named) > research.research_value(0.9, plain)


def test_a_story_about_a_tracked_company_is_a_research_brief_by_default():
    assert research.default_format(research.tags_of("鴻海 AI 伺服器出貨")) == "research_brief"
    assert research.default_format(research.tags_of("油價走跌")) == "news"
    assert research.story_format({}) == "news"
    assert research.story_format({"format": "strategy_study"}) == "strategy_study"
    assert research.story_format({"format": "nonsense"}) == "news"


# --- what a draft must have ----------------------------------------------------------------------


def _version(lang: str, headings: list[str], text: str = "內容") -> LanguageVersion:
    blocks = []
    for heading in headings:
        blocks.append(Block(type="heading", text=heading))
        blocks.append(Block(type="paragraph", text=text, claim_ids=[]))
    return LanguageVersion(lang=lang, title="標題", blocks=blocks)


BRIEF_ZH = ["事件重點", "影響哪些公司", "多空論點", "主要風險", "後續觀察"]
BRIEF_EN = [
    "What happened",
    "Who is affected",
    "The case for and against",
    "Risks",
    "What to watch",
]


def test_a_research_brief_needs_its_parts_in_every_language():
    whole = [_version("zh-TW", BRIEF_ZH), _version("en", BRIEF_EN)]
    assert research.outline_problems("research_brief", whole) == []
    short = [_version("zh-TW", BRIEF_ZH[:2]), _version("en", BRIEF_EN)]
    (problem,) = research.outline_problems("research_brief", short)
    assert problem.startswith("zh-TW") and "多空論點" in problem and "後續觀察" in problem
    assert research.outline_problems("news", short) == [], "news has no outline"


def test_a_company_report_and_a_strategy_study_have_their_own_parts():
    report = [
        "公司概況",
        "營運與財務",
        "估值與市場預期",
        "多方論點",
        "空方論點",
        "主要風險",
        "後續觀察",
        "資料限制",
    ]
    assert research.outline_problems("company_report", [_version("zh-TW", report)]) == []
    study = ["策略規則", "資料與成本假設", "樣本內結果", "樣本外結果", "限制與失效條件"]
    assert research.outline_problems("strategy_study", [_version("zh-TW", study)]) == []
    (problem,) = research.outline_problems("strategy_study", [_version("zh-TW", study[:3])])
    assert "樣本外結果" in problem


def test_a_research_piece_never_says_a_rule_fires_now():
    fires = _version("zh-TW", ["策略規則"], text="台積電目前已符合進場條件")
    (problem,) = research.signal_problems([fires])
    assert "符合進場條件" in problem
    history = _version("zh-TW", ["策略規則"], text="2021 年至 2025 年間共出現 31 次進場條件")
    assert research.signal_problems([history]) == []
    english = LanguageVersion(
        lang="en",
        title="A study",
        blocks=[Block(type="paragraph", text="The rule currently triggers on NVDA", claim_ids=[])],
    )
    assert research.signal_problems([english])
    assert research.draft_problems("news", [fires]) == [], "only research formats"


def test_each_format_lays_out_both_sides_and_its_risks():
    ids = {"a", "b", "c", "d", "e", "f"}
    ok = research.stance_problems(
        "company_report", claim_ids=ids, bull=["a", "b"], bear=["c", "d"], risk=["e", "f"],
        inferences=[("A 的訂單經由 B 進到 C", ["a", "c"])],
    )  # fmt: skip
    assert ok == []
    thin = research.stance_problems(
        "company_report", claim_ids=ids, bull=["a"], bear=[], risk=["e"], inferences=[]
    )
    assert any("2 claim(s) for" in p for p in thin) and any("against" in p for p in thin)
    one_sided = research.stance_problems(
        "research_brief", claim_ids=ids, bull=["a"], bear=[], risk=[], inferences=[]
    )
    assert any("one claim against or one risk" in p for p in one_sided)
    stray = research.stance_problems(
        "research_brief", claim_ids=ids, bull=["z"], bear=["a"], risk=[],
        inferences=[("無據的推論", [])],
    )  # fmt: skip
    assert any("not in claim_ids" in p for p in stray)
    assert any("based_on" in p for p in stray)
    assert (
        research.stance_problems("news", claim_ids=ids, bull=[], bear=[], risk=[], inferences=[])
        == []
    )


# --- the backtest --------------------------------------------------------------------------------


def test_the_indicators_read_only_the_past():
    closes = [float(x) for x in range(1, 31)]
    assert backtest.sma(closes, 5)[3] is None and backtest.sma(closes, 5)[4] == 3.0
    assert backtest.highest(closes, 3)[3] == 3.0, "the three days before, not today"
    assert backtest.rsi(closes, 14)[14] == 100.0, "only gains"
    falling = list(reversed(closes))
    assert backtest.rsi(falling, 14)[20] == 0.0


@pytest.mark.parametrize("key", list(backtest.STRATEGIES))
def test_every_rule_trades_at_the_next_open_after_its_signal(key):
    history = bars(900)
    result = backtest.run(history, key, backtest.costs_for("us", "NVDA"))
    by_day = {b.d: b for b in history}
    assert result.trades, f"{key} made no trade on a series built to have some"
    for trade in result.trades:
        assert trade.entered > history[backtest.WARM_UP].d
        assert trade.entry == pytest.approx(by_day[trade.entered].o * (1 + backtest.SLIPPAGE))
    assert result.split == history[int(900 * backtest.IN_SAMPLE)].d
    assert result.in_sample.end < result.out_sample.start
    assert result.in_sample.trades + result.out_sample.trades == len(result.trades)
    assert -1 < result.out_sample.max_drawdown <= 0


def test_costs_are_charged_and_taiwan_pays_its_tax():
    history = bars(900)
    free = backtest.Costs(0, 0, "", "")
    paid = backtest.costs_for("tw", "2330")
    assert paid.sell == pytest.approx(0.001425 + 0.003 + 0.0005)
    assert backtest.costs_for("tw", "0050").sell == pytest.approx(0.001425 + 0.001 + 0.0005)
    gross = backtest.run(history, "breakout_20", free)
    net = backtest.run(history, "breakout_20", paid)
    assert len(gross.trades) == len(net.trades)
    assert all(n.ret < g.ret for g, n in zip(gross.trades, net.trades, strict=True))


def test_a_short_history_is_not_tested_and_an_unknown_rule_is_refused():
    with pytest.raises(backtest.BacktestError, match="at least 400"):
        backtest.run(bars(300), "breakout_20", backtest.costs_for("us", "AMD"))
    with pytest.raises(backtest.BacktestError, match="no strategy"):
        backtest.run(bars(500), "moon", backtest.costs_for("us", "AMD"))


def test_the_evidence_states_the_rule_the_costs_and_both_periods():
    result = backtest.run(bars(900), "trend_pullback", backtest.costs_for("tw", "2330"))
    text = backtest.render(result, name="台積電", symbol="2330", market="tw", source="TWSE")
    for words in (
        "【策略規則】",
        "進場條件：",
        "成本假設：",
        "證交稅 0.3%",
        "【樣本內結果】",
        "【樣本外結果】",
    ):
        assert words in text
    assert f"樣本內交易次數：{result.in_sample.trades} 筆" in text
    assert "未還原股利" in text, "Taiwan's prices say they are not dividend-adjusted"
    assert "不代表未來表現" in text and "不是交易建議" in text


# --- the price record ----------------------------------------------------------------------------


def test_the_price_record_gives_its_figures_and_what_it_cannot_say():
    history = bars(400)
    record = snapshot.snapshot(history)
    assert record.close == history[-1].c and record.last == history[-1].d
    assert record.high_52w >= record.close >= record.low_52w
    assert dict(record.returns)["近 1 年"] == pytest.approx(history[-1].c / history[-253].c - 1)
    text = snapshot.render(record, name="美光", symbol="MU", market="us", source="Tiingo")
    assert f"收盤價 {record.close:,.2f} 美元" in text
    assert "【資料限制】" in text and "沒有 美光 的財務報表" in text
    assert snapshot.snapshot(bars(80, volume=False)).volume_ratio is None
    with pytest.raises(snapshot.SnapshotError):
        snapshot.snapshot(bars(30))
