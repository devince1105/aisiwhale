"""D-130: English left in the Chinese, and languages that disagree on a year or a percentage."""

import uuid

import pytest

from autora.domains.newsroom.articles import Block, LanguageVersion
from autora.domains.newsroom.bilingual import mismatch_problems, untranslated_problems

CLAIM = uuid.uuid4()


def _version(lang, *blocks, title=None, summary=None):
    return LanguageVersion(
        lang=lang,
        title=title or ("標題" if lang.startswith("zh") else "A title"),
        summary=summary,
        blocks=[Block(type=kind, text=text, claim_ids=[CLAIM]) for kind, text in blocks],
    )


@pytest.mark.parametrize(
    ("text", "word"),
    [("Bitquery的追蹤顯示，75.35 million XRP仍在六個帳戶中。", "million"),
     ("這可能讓USDC取得更多 traction。", "traction"),
     ("事發時約值$157.48 million。", "million"),
     ("根據來源：The city says the microgrid works.", "microgrid")],
)  # fmt: skip
def test_english_left_in_the_chinese_is_refused(text, word):
    [issue] = untranslated_problems([_version("zh-TW", ("paragraph", text))])
    assert issue.startswith("zh-TW block 1 (paragraph)") and word in issue


@pytest.mark.parametrize(
    "text",
    ["BlackRock Investment Institute在《Weekly market commentary》中表示。",
     "AI for Good Lab將延續糧食安全研究。",
     "Lumen City的Harbor District微電網啟用，4 MWh儲能。",
     "這可能讓USDC取得更多吸引力（traction）。",
     "根據來源：「The city says the microgrid works.」",
     "詳見 https://example.test/some-path 。",
     "iPhone與eVTOL的出貨。"],
)  # fmt: skip
def test_names_titles_quotes_and_glosses_are_not(text):
    assert untranslated_problems([_version("zh-TW", ("paragraph", text))]) == []


def test_a_quote_block_and_the_english_version_are_left_alone():
    assert untranslated_problems([_version("zh-TW", ("quote", "「it is a milestone」"))]) == []
    assert untranslated_problems([_version("en", ("paragraph", "the market rallied"))]) == []


def test_the_title_too():
    [issue] = untranslated_problems(
        [_version("zh-TW", ("paragraph", "正文。"), title="更多 traction")]
    )
    assert issue.startswith("zh-TW title")


def test_years_and_percentages_must_agree_paragraph_by_paragraph():
    zh = _version("zh-TW", ("heading", "重點"), ("paragraph", "聯準會將利率目標區間維持在4.5%。"))
    en = _version(
        "en", ("heading", "Key points"), ("paragraph", "In 2026 the Fed held the target at 4.50%.")
    )
    [issue] = mismatch_problems([zh, en])
    assert issue.startswith("block 2: the years differ between zh-TW (none) and en (2026)")


def test_agreeing_or_differently_built_versions_pass():
    zh = _version("zh-TW", ("paragraph", "2026年9月，殖利率升至4.5％。"))
    en = _version("en", ("paragraph", "In September 2026 the yield rose to 4.5 percent."))
    assert mismatch_problems([zh, en]) == []
    restructured = _version("en", ("paragraph", "2025."), ("paragraph", "More."))
    assert mismatch_problems([zh, restructured]) == []


def test_an_amount_at_the_wrong_scale_is_refused():
    zh = _version("zh-TW", ("paragraph", "外資賣超台股338億元，央行收回1,537億元。"))
    en = _version(
        "en",
        ("paragraph", "Foreign investors sold NT$338 billion; the bank withdrew NT$153.7 billion."),
    )
    [issue] = mismatch_problems([zh, en])
    assert issue.startswith("block 1: 338億 is not 338 billion")


def test_amounts_converted_right_or_left_out_pass():
    zh = _version("zh-TW", ("paragraph", "仍有7,535萬枚XRP，約值1.57億美元，另有3億元未計。"))
    en = _version("en", ("paragraph", "75.35 million XRP remain, worth about $157 million."))
    assert mismatch_problems([zh, en]) == []
