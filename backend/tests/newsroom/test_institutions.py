"""D-058: a 機構觀點 paragraph reports one institution's view, from that institution's own site."""

import uuid

from autora.domains.newsroom import institutions, markets
from autora.domains.newsroom.articles import Block, LanguageVersion

FIDELITY_PAGE = (
    "https://institutional.fidelity.com/advisors/insights/series/fidelity-market-signals-weekly"
)
VANGUARD_PAGE = (
    "https://corporate.vanguard.com/content/corporatesite/us/en/corp/vemo/ai-buildout.html"
)
BLACKROCK_PAGE = "https://www.blackrock.com/us/individual/insights/blackrock-investment-institute/weekly-commentary"
NEWS_PAGE = "https://www.investmentnews.com/equities/blackrock-flags-ai-energy-shocks/266293"

A, B = uuid.uuid4(), uuid.uuid4()


def _version(*blocks: Block) -> LanguageVersion:
    return LanguageVersion(
        lang="zh-TW", title="標題", blocks=[Block(type="heading", text="h"), *blocks]
    )


def test_a_figure_from_another_firm_is_not_this_firm_s_estimate():
    """The Fidelity draft: Vanguard's US$300–570bn, written as "Fidelity的另一項估計"."""
    draft = _version(
        Block(type="paragraph", text="Fidelity估計…；Fidelity的另一項估計顯示…5700億美元。",
              claim_ids=[A, B])
    )  # fmt: skip
    issues = institutions.attribution_problems([draft], {A: {FIDELITY_PAGE}, B: {VANGUARD_PAGE}})
    assert len(issues) == 1
    assert f"claim {B} comes from corporate.vanguard.com, not from 富達's own site" in issues[0]
    assert "zh-TW block 2" in issues[0]


def test_news_coverage_is_not_the_institution_speaking():
    """The first BlackRock draft: InvestmentNews on BlackRock's annual outlook."""
    draft = _version(
        Block(type="paragraph", text="InvestmentNews報道，BlackRock維持建設性看法。", claim_ids=[A])
    )
    [issue] = institutions.attribution_problems([draft], {A: {NEWS_PAGE}})
    assert "www.investmentnews.com" in issue and "貝萊德" in issue


def test_a_paragraph_must_say_whose_view_it_is():
    draft = _version(Block(type="paragraph", text="殖利率上升主要由成長推動。", claim_ids=[A]))
    [issue] = institutions.attribution_problems([draft], {A: {FIDELITY_PAGE}})
    assert "says whose view it is" in issue


def test_the_institution_s_own_words_pass_in_either_language():
    """The published BlackRock article, and the same in English."""
    zh = _version(Block(type="paragraph", text="BlackRock估計，美國年度融資需求…", claim_ids=[A]))
    en = LanguageVersion(
        lang="en", title="Title",
        blocks=[Block(type="paragraph", text="BlackRock estimated that...", claim_ids=[A])],
    )  # fmt: skip
    assert institutions.attribution_problems([zh, en], {A: {BLACKROCK_PAGE}}) == []
    # two firms named, each citing its own publication: both are reported, neither borrowed
    both = _version(Block(type="paragraph", text="富達與先鋒都估計…", claim_ids=[A, B]))
    sources = {A: {FIDELITY_PAGE}, B: {VANGUARD_PAGE}}
    assert institutions.attribution_problems([both], sources) == []


def test_names_are_read_as_names():
    assert [i.key for i in institutions.named_in("UBS and J.P. Morgan")] == ["ubs", "jpmorgan"]
    assert institutions.named_in("a subsidy for BNYX") == []
    assert [i.key for i in institutions.named_in("摩根大通私人銀行")] == ["jpmorgan"]
    jpm = institutions.named_in("JPMorgan")[0]
    assert institutions.speaks_for("https://privatebank.jpmorgan.com/latam/x", jpm)
    assert not institutions.speaks_for("https://jpmorgan.com.evil.example/x", jpm)


def test_the_searches_look_where_the_check_looks():
    searched = {
        d
        for s in markets.SOURCES
        if s.config.get("section") == "institutions"
        for d in s.config.get("domains", [])
    }
    assert searched == {d for i in institutions.INSTITUTIONS for d in i.domains}
