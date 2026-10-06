"""D-212: a brief names its section in its own words, when a person did not choose one."""

from autora.domains.newsroom.sources import SECTION_WORDS, SECTIONS, section_from_words


def test_the_words_of_a_brief_say_its_section():
    # 10/05's brief: Taiwan stocks, twice, and nothing else
    brief = (
        "2026年10月5日台積電衝上2580元、帶動台股大漲逾千點突破49600點創新高，"
        "收盤表現與五萬點關卡市場怎麼看"
    )
    assert section_from_words(brief) == "tw"
    assert section_from_words("道瓊收黑、標普跌 0.7%") == "us"
    assert section_from_words("寫一篇 NVDA 財報") == "us"
    assert section_from_words("比特幣站上 10 萬美元") == "crypto"
    assert section_from_words("黃金與原油同步走高，金價創高") == "gold"  # gold twice, oil once
    assert section_from_words("新台幣午盤貶 5.9 分") == "fx"
    assert section_from_words("巴菲特 13F 持股申報") == "holdings"
    assert section_from_words("寫一篇機構持股的報導") == "holdings"  # 大戶持股's new name (10/06)


def test_latin_words_count_only_whole_and_a_tie_goes_to_the_stock_market():
    assert section_from_words("Taiwan 經濟") is None  # TAIWAN is not AI
    assert section_from_words("metaverse 熱潮") is None  # METAVERSE is not META
    assert section_from_words("ai 伺服器") == "ai"  # any case
    assert section_from_words("台積電 AI 伺服器") == "tw"  # one each: the stock market first


def test_no_word_no_section():
    assert section_from_words("今天天氣很好") is None
    assert section_from_words("") is None


def test_every_section_named_is_one_the_site_has():
    assert set(SECTION_WORDS) <= set(SECTIONS)
