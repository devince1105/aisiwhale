"""Permission rules for newsroom tools and actions (logs/platform/07_PERMISSION_MODEL.md §3).

D-001: publishing needs a human approval by default. ``approve_article`` by the system (automatic
approval after a passed fact-check) is only allowed when the company policy
``newsroom.auto_approve_if_fact_check_passed`` is true; otherwise it needs a human.

D-157: an article's approval nobody answered goes to the CEO, who approves or rejects it
(``approve_article`` by the ``ceo`` role, only for an approval delegated to her, only with a
passed fact-check), while the company policy ``newsroom.ceo_decides_when_unanswered`` is on (the
default; false brings back "expire and ask a person again").

D-252: it goes to her within ``newsroom.ceo_after_hours`` (8) — and while she is at work, so the
same day — not after 24 hours; and she publishes it unless it breaks the advisory law or has an
error she can name. How long news stays worth running is per section
(``newsroom.shelf_life_hours``): timeliness alone turns down only a piece that was already past
``HARD_LIMIT_FACTOR`` times its shelf life when the desk asked for approval.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Literal

from autora.company import policy as company_policy
from autora.runtime.policy import Limit, PolicyEngine, Rule, allow

AUTO_APPROVE_KEY = "newsroom.auto_approve_if_fact_check_passed"
CEO_DECIDES_WHEN_UNANSWERED_KEY = "newsroom.ceo_decides_when_unanswered"

VIP_GUIDELINES_KEY = "newsroom.vip_guidelines"
DEFAULT_VIP_GUIDELINES = (
    "深度分析、整理多個來源的數據比較、長期追蹤的主題，可以設為 VIP；"
    "即時新聞、單一事件快訊與一般市場動態維持免費。VIP 約占全部文章的三成以內。"
)
"""D-159: which articles the editor-in-chief makes VIP (members-only) when she accepts them. A
company policy, so the operator can change it without a release."""


def vip_guidelines(policies: Mapping[str, Any]) -> str:
    value = policies.get(VIP_GUIDELINES_KEY)
    return value.strip() if isinstance(value, str) and value.strip() else DEFAULT_VIP_GUIDELINES


def ceo_decides_when_unanswered(policies: Mapping[str, Any]) -> bool:
    """D-157: on unless the company has turned it off."""
    return policies.get(CEO_DECIDES_WHEN_UNANSWERED_KEY, True) is not False


CEO_AFTER_HOURS_KEY = "newsroom.ceo_after_hours"
DEFAULT_CEO_AFTER_HOURS = 8.0
"""D-252: at most how long an article's approval waits for a person before the CEO decides."""


def ceo_after_hours(policies: Mapping[str, Any]) -> float:
    value = policies.get(CEO_AFTER_HOURS_KEY)
    if isinstance(value, bool) or not isinstance(value, int | float) or not 0 < value <= 24:
        return DEFAULT_CEO_AFTER_HOURS
    return float(value)


SHELF_LIFE_KEY = "newsroom.shelf_life_hours"
DEFAULT_SHELF_LIFE = 72
DEFAULT_SHELF_LIVES: dict[str, int] = {
    "crypto": 48,
    "fx": 48,
    "gold": 48,
    "commodities": 48,
    "tw": 72,
    "us": 72,
    "ai": 120,
    "holdings": 336,
    "figures": 336,
    "institutions": 336,
    "research": 720,  # D-256: a company report holds for a month
    "strategy": 2160,  # and a strategy study, being history, for a quarter
}
"""D-252: how many hours after its story was found news in each section is still timely. A piece
about one day's price move or level is a day's, whatever its section (the CEO is told so)."""
HARD_LIMIT_FACTOR = 3
"""Past this many shelf lives when the desk asked for approval, it is stale: turned down."""


def shelf_life_hours(policies: Mapping[str, Any], section: str | None) -> int:
    """The section's shelf life, the company's if it set one (a mapping, by section)."""
    given = policies.get(SHELF_LIFE_KEY)
    if isinstance(given, Mapping):
        value = given.get(section or "")
        if isinstance(value, int | float) and not isinstance(value, bool) and value > 0:
            return int(value)
    return DEFAULT_SHELF_LIVES.get(section or "", DEFAULT_SHELF_LIFE)


TOPIC_MIX_KEY = "newsroom.topic_mix"
"""D-253: what the desk covers, in shares of the stories it commissions — ``{"focus_terms":
[...], "crypto": 0.01, "other": 0.09}``. A story is *focus* when its title or summary names one
of the terms, *crypto* when it is in the crypto section, *other* otherwise. Not set: no mix, the
desk chooses from everything as before."""

DEFAULT_FOCUS_TERMS = (
    *("NVIDIA", "Nvidia", "輝達", "黃仁勳", "TSMC", "台積電", "AI 伺服器", "AI伺服器", "GPU"),
    *("HBM", "CoWoS", "先進封裝", "資料中心", "data center", "鴻海", "Foxconn", "廣達", "緯創"),
    *("緯穎", "世芯", "創意電子", "日月光", "SK hynix", "SK 海力士", "Micron", "美光", "AMD"),
    *("Broadcom", "博通", "ASML", "AI chip", "AI 晶片"),
)
"""D-253's draft: NVIDIA, TSMC and the AI supply chain around them."""

Bucket = Literal["focus", "crypto", "other"]


@dataclass(frozen=True)
class TopicMix:
    focus_terms: tuple[str, ...]
    crypto: float
    """The most of the commissioned stories crypto may be (0.01: one in a hundred)."""
    other: float
    """The most that is neither focus nor crypto may be."""

    def bucket(self, *, section: str | None, text: str) -> Bucket:
        if section == "crypto":
            return "crypto"
        lowered = text.lower()
        if any(term.lower() in lowered for term in self.focus_terms):
            return "focus"
        return "other"

    def may_add(self, counts: Mapping[str, int], bucket: Bucket) -> bool:
        """Whether one more ``bucket`` story keeps its share within the mix, counted over the
        stories commissioned lately (``counts``, by bucket). Focus always may."""
        if bucket == "focus":
            return True
        total = sum(counts.values()) + 1
        return (counts.get(bucket, 0) + 1) / total <= getattr(self, bucket)


def topic_mix(policies: Mapping[str, Any]) -> TopicMix | None:
    value = policies.get(TOPIC_MIX_KEY)
    if not isinstance(value, Mapping):
        return None
    terms = value.get("focus_terms")
    terms = (
        tuple(t for t in terms if isinstance(t, str) and t.strip())
        if isinstance(terms, list)
        else DEFAULT_FOCUS_TERMS
    )

    def share(key: str, default: float) -> float:
        given = value.get(key)
        if isinstance(given, bool) or not isinstance(given, int | float) or not 0 <= given <= 1:
            return default
        return float(given)

    return TopicMix(terms or DEFAULT_FOCUS_TERMS, share("crypto", 0.01), share("other", 0.09))


# D-002: which languages articles are written and published in (company policy, not code)
PRIMARY_LANG_KEY = "newsroom.primary_lang"
LANGS_KEY = "newsroom.langs"
REQUIRE_ALL_LANGS_KEY = "newsroom.require_all_langs"
LANGUAGE_DEFAULTS = {
    PRIMARY_LANG_KEY: "zh-TW",
    LANGS_KEY: ["zh-TW", "en"],
    REQUIRE_ALL_LANGS_KEY: True,
}


# T-510: how much a source must be trusted to support a claim alone
MIN_TRUST_KEY = "newsroom.min_source_trust"
DEFAULT_TRUST_KEY = "newsroom.default_source_trust"
TRUST_DEFAULTS = {MIN_TRUST_KEY: "0.4", DEFAULT_TRUST_KEY: "0.5"}


def trust_policy(policies: Mapping[str, Any]) -> tuple[Decimal, Decimal]:
    """(minimum trust to support a claim alone, trust of evidence no source listed)."""
    return (
        Decimal(str(policies.get(MIN_TRUST_KEY, TRUST_DEFAULTS[MIN_TRUST_KEY]))),
        Decimal(str(policies.get(DEFAULT_TRUST_KEY, TRUST_DEFAULTS[DEFAULT_TRUST_KEY]))),
    )


@dataclass(frozen=True)
class LanguagePolicy:
    primary: str
    langs: tuple[str, ...]
    require_all: bool


def language_policy(policies: Mapping[str, Any]) -> LanguagePolicy:
    """The company's language rules (D-002), defaults filled in; the primary is always a
    language."""
    primary = policies.get(PRIMARY_LANG_KEY) or LANGUAGE_DEFAULTS[PRIMARY_LANG_KEY]
    langs = list(policies.get(LANGS_KEY) or LANGUAGE_DEFAULTS[LANGS_KEY])
    if primary not in langs:
        langs.insert(0, primary)
    require_all = policies.get(REQUIRE_ALL_LANGS_KEY)
    return LanguagePolicy(
        primary=primary,
        langs=tuple(langs),
        require_all=LANGUAGE_DEFAULTS[REQUIRE_ALL_LANGS_KEY]
        if require_all is None
        else bool(require_all),
    )


WRITERS_AND_READERS = (
    "researcher",
    "analyst",
    "writer",
    "editor",
    "marketing",
    "editor_in_chief",
    "ceo",
)


def _auto_approve_enabled(args, facts, policies: Mapping[str, Any]) -> str | None:
    if policies.get(AUTO_APPROVE_KEY) is True:
        if facts.get("fact_check_passed") is True:
            return None
        return "fact-check has not passed"
    return f"{AUTO_APPROVE_KEY} is off (D-001: a human approves publication)"


def _delegated_to_the_ceo(args, facts, policies: Mapping[str, Any]) -> str | None:
    """D-157: the CEO approves only an article whose approval was delegated to her."""
    if facts.get("delegated") is not True:
        return "the CEO decides only an approval nobody answered (D-157)"
    if facts.get("fact_check_passed") is not True:
        return "fact-check has not passed"
    return None


def _article_published(args, facts, policies) -> str | None:
    state = facts.get("article_state")
    return None if state == "PUBLISHED" else f"article is {state or 'unknown'}, not PUBLISHED"


def _within_campaign_cap(args, facts, policies) -> str | None:
    try:
        spent, amount, cap = (float(facts["campaign_spent"]), float(args["amount"]),
                              float(facts["campaign_cap"]))  # fmt: skip
    except (KeyError, TypeError, ValueError):
        return "campaign cap or amount unknown"
    return None if spent + amount <= cap else f"{spent + amount} exceeds campaign cap {cap}"


ACTIONS = {
    "web_search": "read",
    "fetch_url": "write",  # stores an evidence snapshot
    "compare_13f": "write",  # stores a 13F comparison as evidence (D-037)
    "market_snapshot": "write",  # stores a stock's price record as evidence (D-256)
    "run_backtest": "write",  # stores a strategy's backtest as evidence (D-256)
    "read_evidence": "read",
    "search_evidence": "read",
    "create_claim": "write",
    "link_evidence": "write",
    "list_claims": "read",
    "write_draft": "write",
    "read_draft": "read",
    "run_fact_check": "write",
    "request_revision": "write",
    "accept_draft": "write",
    "final_review": "write",  # the editor-in-chief's (D-110)
    "approve_article": "write",
    "decide_unanswered_article": "write",  # D-157: the CEO, on an article nobody approved
    "publish_article": "write",
    "create_distribution": "write",
    "search_images": "read",
    "set_cover": "write",
    "generate_cover": "write",
    "spend_ad_budget": "write",
    "commission_story": "write",
    "commission_company_report": "write",  # D-256
    "commission_strategy_study": "write",  # D-256
}

RULES: list[Rule] = [
    *allow("web_search", "researcher", "marketing"),
    *allow("fetch_url", "researcher", "marketing"),
    *allow("compare_13f", "researcher"),
    *allow("market_snapshot", "researcher"),
    *allow("run_backtest", "researcher"),
    *allow("read_evidence", *WRITERS_AND_READERS),
    *allow("search_evidence", *WRITERS_AND_READERS),
    *allow("create_claim", "analyst"),
    *allow("link_evidence", "analyst"),
    *allow("list_claims", *WRITERS_AND_READERS),
    *allow("write_draft", "writer"),
    *allow("read_draft", "writer", "editor", "editor_in_chief", "marketing", "ceo"),
    *allow("run_fact_check", "editor"),
    *allow("request_revision", "editor"),
    *allow("accept_draft", "editor"),
    *allow("final_review", "editor_in_chief"),
    *allow(
        "approve_article",
        "system",
        limit=Limit(_auto_approve_enabled, over="needs_approval", description="auto-approval"),
    ),
    *allow(
        "approve_article",
        "ceo",
        limit=Limit(_delegated_to_the_ceo, over="deny", description="delegated approvals only"),
    ),
    *allow("decide_unanswered_article", "ceo"),
    *allow("publish_article", "system"),  # the Publisher service, after APPROVED
    *allow(
        "create_distribution",
        "marketing",
        limit=Limit(_article_published, over="deny", description="published articles only"),
    ),
    *allow("search_images", "marketing"),
    *allow("set_cover", "marketing"),  # D-142: the article's cover, before it is approved
    *allow("generate_cover", "marketing"),  # D-145: drawn, when the library has none
    *allow(
        "spend_ad_budget",
        "marketing",
        limit=Limit(_within_campaign_cap, over="needs_approval", description="campaign cap"),
    ),
    # The desk head may commission a story, and may start the work it commissions. The cap on
    # how much work that is belongs to the company, not to the newsroom: this rule points at
    # the company's own limit so a newsroom cannot give itself a bigger day (T-605b).
    *allow("commission_story", "editor_in_chief"),
    *allow("commission_company_report", "editor_in_chief"),
    *allow("commission_strategy_study", "editor_in_chief"),
    *allow(
        "instantiate_workflow",
        "editor_in_chief",
        limit=Limit(
            company_policy.max_workflows,
            over="deny",
            description="workflows per cycle",
        ),
    ),
]


def register(engine: PolicyEngine) -> None:
    for action, side_effect in ACTIONS.items():
        engine.declare(action, side_effect)
    engine.add(RULES)
