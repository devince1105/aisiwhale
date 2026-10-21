"""Investment research (D-256): what the desk writes once news is not enough.

Readers do not lack news; they lack what it means for the companies they hold. So a story about
a listed company is written as a **research brief** — what happened, which companies it reaches
and through what, the public evidence for and against, the risks, what to watch — and the desk
writes two kinds of piece no news item starts:

- a **company report** (個股研究): a tracked company's business, results, valuation context, the
  case for and against, the risks and what the data cannot say;
- a **strategy study** (策略研究): one fixed trading rule tested on a tracked stock's history by
  this newsroom's own code (``backtest.py``), in-sample and out-of-sample, with its costs.

A story's format lives in ``stories.seed.format``; every desk reads it from there, so the article
workflow is the same one (D-253's mix counts it, approval and publication are unchanged). The
newsroom still gives no advice (D-035): the case for and against is laid side by side with no
verdict, a forecast is somebody's, and a strategy study reports how a rule *did*, never that it
fires today.

This module is the desk's rules, kept free of the database: the tags the editor-in-chief ranks
candidates by, the brief each desk is given per format, and the checks a draft must pass.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from autora.domains.newsroom import holdings

FORMAT = "format"
"""``stories.seed.format``: one of ``FORMATS``. Not set: ``news``, as every story before D-256."""

Format = Literal["news", "research_brief", "company_report", "strategy_study"]
FORMATS: tuple[Format, ...] = ("news", "research_brief", "company_report", "strategy_study")
RESEARCH_FORMATS = frozenset({"research_brief", "company_report", "strategy_study"})

SYMBOL = "symbol"
"""``stories.seed.symbol``: the tracked stock a company report or strategy study is about."""
MARKET = "market"
STRATEGY = "strategy"
"""``stories.seed.strategy``: the rule a strategy study tests (``backtest.STRATEGIES``)."""

RESEARCH_SECTION = "research"
STRATEGY_SECTION = "strategy"
SECTION_OF_FORMAT: dict[str, str] = {
    "company_report": RESEARCH_SECTION,
    "strategy_study": STRATEGY_SECTION,
}
"""Where a format's articles are on the site: a person-given section (``seed.section``). A research
brief stays in the section its sources name (台股, 美股, AI 科技)."""


def story_format(seed: Mapping[str, Any] | None) -> Format:
    value = (seed or {}).get(FORMAT)
    return value if value in FORMATS else "news"


# --- what the editor-in-chief ranks by ------------------------------------------------------------

EVENTS: dict[str, tuple[str, ...]] = {
    "earnings": (
        *("財報", "營收", "獲利", "淨利", "毛利率", "EPS", "每股盈餘", "法說"),
        *("earnings", "revenue", "quarterly results", "net income", "gross margin"),
    ),
    "guidance": ("財測", "展望", "指引", "guidance", "outlook", "forecast"),
    "orders_capex": (
        *("訂單", "資本支出", "擴產", "產能", "建廠", "採購"),
        *("order", "capex", "capital expenditure", "capacity", "new fab", "purchase"),
    ),
    "product_tech": (
        *("發表", "推出", "量產", "新品", "製程", "架構", "晶片"),
        *("launch", "unveil", "mass production", "process node", "architecture"),
    ),
    "policy": (
        *("出口管制", "關稅", "制裁", "禁令", "補助", "法規"),
        *("export control", "tariff", "sanction", "export ban", "subsidy", "regulat"),
    ),
    "corporate": (
        *("併購", "收購", "合併", "庫藏股", "股利", "增資", "減資", "分割"),
        *("acquisition", "acquire", "merger", "buyback", "dividend", "spin-off", "stock split"),
    ),
    "legal": ("訴訟", "調查", "罰款", "lawsuit", "investigation", "probe", "fined"),
}
"""Material events: the kinds of news that can change what a company earns or is worth. Matched
in a story's title and summary, case aside: a Chinese word anywhere, an English one from the start
of a word with at most a short ending (orders, launched, regulatory — not border, not bank)."""

_EVENT_WORDS = {
    kind: [
        re.compile(rf"\b{re.escape(w.lower())}\w{{0,4}}\b")
        if w.isascii()
        else re.compile(re.escape(w.lower()))
        for w in words
    ]
    for kind, words in EVENTS.items()
}


@dataclass(frozen=True)
class ResearchTags:
    stocks: tuple[holdings.Stock, ...]
    events: tuple[str, ...]

    @property
    def names(self) -> str:
        return ", ".join(f"{s.zh}({s.symbol})" for s in self.stocks)


def tags_of(text: str) -> ResearchTags:
    """The tracked companies a story names and the material events it is about."""
    from autora.domains.newsroom import holdings  # holdings imports the tools, which import this

    lowered = text.lower()
    events = tuple(
        kind for kind, words in _EVENT_WORDS.items() if any(w.search(lowered) for w in words)
    )
    return ResearchTags(stocks=tuple(holdings.stocks_named(text, limit=4)), events=events)


def research_value(score: float, tags: ResearchTags) -> float:
    """How much a candidate is worth to an investment-research desk, 0..1: the story desk's own
    score (corroboration, freshness, trust) for half; a named listed company and a material event
    for the rest. A story about nobody in particular can still be news, never a research brief."""
    company = 0.3 if tags.stocks else 0.0
    event = 0.2 if tags.events else 0.0
    return round(min(1.0, 0.5 * max(0.0, min(1.0, score)) + company + event), 3)


def default_format(tags: ResearchTags) -> Format:
    """A story about a tracked company is a research brief; anything else stays news."""
    return "research_brief" if tags.stocks else "news"


# --- what each desk is told, per format -----------------------------------------------------------

STANCES_NOTE = (
    "Sort the claims into the case for (bull_claim_ids), the case against (bear_claim_ids) and the "
    "risks (risk_claim_ids). A side is facts and attributed views — a result, a figure, an analyst "
    "or a company saying so — never the newsroom's own call, and neither side wins: the article "
    "lays them side by side and draws no verdict (D-035). A claim may be on one side only."
)

INFERENCE_NOTE = (
    "inferences: the desk's own reasoning that links facts (how an order reaches a supplier, which "
    "line of a company a policy touches), each built only on the claims it lists in based_on. An "
    "inference explains a connection; it never says what a price will do, what to buy or what a "
    "company is worth. The article writes each one as 推論：… / Inference: …, citing its claims."
)

BRIEFS: dict[str, dict[str, str]] = {
    "research_brief": {
        "researcher": (
            "Format: research brief (D-256). The story is news about a listed company; the article "
            "explains what it means for the companies it reaches. Capture: the primary record (the "
            "company's release, filing, results or the official statement), coverage that names "
            "who is affected (customers, suppliers, competitors), and a view from each side "
            "(analysts or the companies themselves, attributed). For a tracked stock the story "
            "names, call market_snapshot: the share price's own record, computed by this newsroom."
        ),
        "analyst": (
            "Format: research brief (D-256). Besides the claims, " + STANCES_NOTE + " At least one "
            "claim for the case for, and one against or one risk. " + INFERENCE_NOTE + " List what "
            "the evidence could not tell (data_gaps), e.g. no valuation figures."
        ),
        "writer": (
            "Format: research brief (D-256). Headings, in this order, in every language: "
            "事件重點 / What happened; 影響哪些公司 / Who is affected (the path from the event to "
            "each company); 多空論點 / The case for and against (both sides, no verdict); "
            "主要風險 / Risks; 後續觀察 / What to watch. About 8-14 blocks per language."
        ),
    },
    "company_report": {
        "researcher": (
            "Format: company report (D-256) on the tracked stock above. Capture the company's own "
            "record first — its latest quarterly results release or investor-relations page, and "
            "its annual report or filing (SEC 10-K/10-Q/20-F; for Taiwan, its own results release) "
            "— then independent coverage of its industry position and of analysts' views, each "
            "side. Call market_snapshot for the stock: required, it is the price record and says "
            "what data this newsroom does not hold."
        ),
        "analyst": (
            "Format: company report (D-256). Record claims on the business, the latest results "
            "(revenue, margins, earnings, cash flow — numbers quoted from the record), its "
            "industry position, the share price's record (market_snapshot) and what others say "
            "of its valuation (attributed). "
            + STANCES_NOTE
            + " At least two claims for, two against, "
            "two risks. " + INFERENCE_NOTE + " data_gaps: what this report could not cover and why "
            "(e.g. no EPS series to compute a P/E), quoting the snapshot's data notes."
        ),
        "writer": (
            "Format: company report (D-256). Headings, in this order, in every language: 公司概況 "
            "/ The business; 營運與財務 / Results and financials; 估值與市場預期 / Valuation and "
            "expectations (only figures and attributed views, never a price of our own); 多方論點 "
            "/ The bull case; 空方論點 / The bear case; 主要風險 / Risks; 後續觀察 / What to "
            "watch; 資料限制 / Data limitations. About 12-18 blocks per language, short paragraphs."
        ),
    },
    "strategy_study": {
        "researcher": (
            "Format: strategy study (D-256). Call run_backtest for the stock and strategy above: "
            "it tests the rule on the stored daily prices and captures the result as evidence — "
            "that is the record the article reports. Add a source that explains the rule's idea "
            "(an exchange's or an educator's page on breakouts, trends or mean reversion) only if "
            "it helps; never a page that claims the rule's results."
        ),
        "analyst": (
            "Format: strategy study (D-256). Record number claims from the backtest evidence only: "
            "the rule, the data and cost assumptions, and for the in-sample and out-of-sample "
            "periods the trades, win rate, average win and loss, expectancy, total return, maximum "
            "drawdown and buy-and-hold return. Put a weak or failed result on the case against "
            "(bear_claim_ids) and the limits on risk_claim_ids; a result is never better than the "
            "evidence says. No claim about today's prices or today's signal."
        ),
        "writer": (
            "Format: strategy study (D-256). Headings, in this order, in every language: "
            "策略規則 / The rule; 資料與成本假設 / Data and cost assumptions; "
            "樣本內結果 / In-sample results; 樣本外結果 / Out-of-sample results; "
            "限制與失效條件 / Limits and when it fails. Report how the rule did on history; "
            "never say it fires now, never call a day a buy point (write 進場條件 / entry "
            "condition). About 8-12 blocks per language."
        ),
    },
}


def brief(fmt: str, desk: str) -> str | None:
    return BRIEFS.get(fmt, {}).get(desk)


# --- what a draft must have, per format -----------------------------------------------------------

Topic = tuple[str, tuple[str, ...], tuple[str, ...]]
"""(what the section is, words a Chinese heading for it uses, words an English one uses)."""

OUTLINES: dict[str, tuple[Topic, ...]] = {
    "research_brief": (
        ("事件重點", ("事件", "發生", "重點", "消息"), ("what happened", "event", "news")),
        (
            "影響哪些公司",
            ("影響", "受惠", "傳導", "供應鏈", "相關公司"),
            ("affected", "impact", "supply chain", "read-through", "who"),
        ),
        (
            "多空論點",
            ("多空", "正反", "多方", "空方", "支持與反對"),
            ("bull", "bear", "case for", "case against", "for and against"),
        ),
        ("主要風險", ("風險",), ("risk",)),
        ("後續觀察", ("觀察", "追蹤", "接下來", "關注"), ("watch", "next", "track")),
    ),
    "company_report": (
        ("公司概況", ("公司", "概況", "業務"), ("business", "company", "overview")),
        (
            "營運與財務",
            ("營運", "財務", "營收", "獲利", "財報"),
            ("results", "financial", "revenue", "earnings", "operations"),
        ),
        (
            "估值與市場預期",
            ("估值", "市場預期", "股價", "評價"),
            ("valuation", "expectation", "share price"),
        ),
        ("多方論點", ("多方", "支持"), ("bull", "case for")),
        ("空方論點", ("空方", "反對"), ("bear", "case against")),
        ("主要風險", ("風險",), ("risk",)),
        ("後續觀察", ("觀察", "追蹤", "接下來"), ("watch", "next", "track")),
        ("資料限制", ("限制",), ("limitation", "limits")),
    ),
    "strategy_study": (
        ("策略規則", ("規則", "策略", "條件"), ("rule", "strategy", "condition")),
        ("資料與成本假設", ("資料", "成本", "假設"), ("data", "cost", "assumption")),
        ("樣本內結果", ("樣本內",), ("in-sample", "in sample")),
        ("樣本外結果", ("樣本外",), ("out-of-sample", "out of sample")),
        ("限制與失效條件", ("限制", "失效"), ("limit", "fail")),
    ),
}

CURRENT_SIGNAL = re.compile(
    r"(今天|今日|目前|現在|當前|最新|本週|近日)[^。！？\n]{0,12}(符合|觸發|出現|發出|亮起)"
    r"[^。！？\n]{0,8}(訊號|信號|條件|買訊|賣訊)"
    r"|\b(today|currently|now|this week)\b[^.\n]{0,40}\b(triggers?|triggered|meets?|flash(es)?"
    r"|fires?|fired)\b",
    re.IGNORECASE,
)
"""A strategy that fires now: what a research piece never says (D-256)."""


def _headings(version: Any) -> list[str]:
    return [b.text.lower() for b in version.blocks if b.type == "heading"]


def outline_problems(fmt: str, versions: Iterable[Any]) -> list[str]:
    """The sections a format's draft is missing, per language (empty: none)."""
    outline = OUTLINES.get(fmt)
    if not outline:
        return []
    issues = []
    for version in versions:
        english = version.lang.startswith("en")
        headings = _headings(version)
        missing = [
            name
            for name, zh, en in outline
            if not any(word.lower() in h for h in headings for word in (en if english else zh))
        ]
        if missing:
            issues.append(
                f"{version.lang}: a {fmt} needs a heading for each of its sections — missing "
                + ", ".join(missing)
                + " (D-256: every research piece has the same parts, in every language)"
            )
    return issues


def signal_problems(versions: Iterable[Any]) -> list[str]:
    """Places a research draft says a rule fires now (D-256)."""
    issues = []
    for version in versions:
        texts = [("title", version.title), ("summary", version.summary or "")]
        texts += [(f"block {i}", b.text) for i, b in enumerate(version.blocks, 1)]
        for where, text in texts:
            if match := CURRENT_SIGNAL.search(text):
                issues.append(
                    f"{version.lang} {where}: {match.group(0)!r} says a rule fires now; a research "
                    "piece reports how a rule did on history, never today's signal"
                )
    return issues


def draft_problems(fmt: str, versions: list[Any]) -> list[str]:
    """Everything a research format adds to ``write_draft``'s checks."""
    if fmt not in RESEARCH_FORMATS:
        return []
    return outline_problems(fmt, versions) + signal_problems(versions)


MIN_STANCES: dict[str, tuple[int, int, int]] = {
    "research_brief": (1, 0, 0),
    "company_report": (2, 2, 2),
    "strategy_study": (0, 0, 1),
}
"""(for, against, risks) a format's analysis lists at least. A research brief also needs one
claim against *or* one risk — news rarely has both sides at once."""


def stance_problems(
    fmt: str,
    *,
    claim_ids: set[str],
    bull: list[str],
    bear: list[str],
    risk: list[str],
    inferences: list[tuple[str, list[str]]],
) -> list[str]:
    """What the analysis of a research format is missing (empty: nothing)."""
    if fmt not in RESEARCH_FORMATS:
        return []
    issues = []
    for label, ids in (
        ("bull_claim_ids", bull),
        ("bear_claim_ids", bear),
        ("risk_claim_ids", risk),
    ):
        stray = [i for i in ids if i not in claim_ids]
        if stray:
            issues.append(f"{label} lists claims not in claim_ids: {', '.join(stray)}")
    both = set(bull) & set(bear)
    if both:
        issues.append(f"a claim is on both sides: {', '.join(sorted(both))}")
    need_for, need_against, need_risk = MIN_STANCES[fmt]
    if len(set(bull)) < need_for:
        issues.append(f"a {fmt} needs at least {need_for} claim(s) for (bull_claim_ids)")
    if len(set(bear)) < need_against:
        issues.append(f"a {fmt} needs at least {need_against} claim(s) against (bear_claim_ids)")
    if len(set(risk)) < need_risk:
        issues.append(f"a {fmt} needs at least {need_risk} risk claim(s) (risk_claim_ids)")
    if fmt == "research_brief" and not (bear or risk):
        issues.append("a research brief needs one claim against or one risk: show both sides")
    for text, based_on in inferences:
        if not based_on or any(i not in claim_ids for i in based_on):
            issues.append(f"inference {text[:40]!r}: based_on must list claims in claim_ids")
    return issues
