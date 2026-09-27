"""D-083: a draft's own words name the period — never 今年, 上週, 近期 or "this year" alone."""

import uuid

import pytest

from autora.domains.newsroom.articles import Block, LanguageVersion
from autora.domains.newsroom.timing import vague_time_problems

CLAIM = uuid.uuid4()


def _version(lang, title, *blocks, summary=None):
    return LanguageVersion(
        lang=lang,
        title=title,
        summary=summary,
        blocks=[Block(type=kind, text=text, claim_ids=[CLAIM]) for kind, text in blocks],
    )


@pytest.mark.parametrize(
    "text",
    ["台積電今年營收成長三成。", "上週外資賣超。", "近期美債殖利率走高。", "較去年同期成長。",
     "ETF inflows this year reached $8 billion.", "Yields rose recently.",
     "Year-to-date inflows turned positive."],
)  # fmt: skip
def test_a_period_nobody_can_place_later_is_refused(text):
    [issue] = vague_time_problems([_version("zh-TW", "標題", ("paragraph", text))])
    assert "block 1 (paragraph)" in issue and "never a year the evidence does not give" in issue


def test_named_periods_pass_and_a_quote_says_what_was_said():
    placed = _version(
        "zh-TW",
        "2026年9月21日當週：美債殖利率觸及5%",
        ("paragraph", "截至2026年9月底，據該週評，AI 相關債券發行較2025年同期增加。"),
        ("quote", "「今年的資本支出仍會增加。」"),
        summary="2026年第三季",
    )
    assert vague_time_problems([placed]) == []


def test_the_title_and_summary_too_in_either_language():
    issues = vague_time_problems(
        [_version("en", "Nvidia rallies this week", ("paragraph", "On Sept. 24, 2026."),
                  summary="Shares rose today.")]
    )  # fmt: skip
    assert [i.split(":")[0] for i in issues] == ["en title", "en summary"]


def test_a_word_that_only_contains_one_is_not_refused():
    assert vague_time_problems([_version("en", "Todays", ("paragraph", "Todayville."))]) == []
