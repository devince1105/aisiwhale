"""HD-09: 機構排行's names — the second quarter of 2026's 50 largest 13F filers named, in Taiwan's
words, and nobody else's names changed."""

from autora.domains.newsroom.filers import FILERS, filer_name
from autora.domains.newsroom.holdings import PROFILES
from autora.domains.newsroom.institutions import INSTITUTIONS
from autora.domains.newsroom.language import taiwan_usage_problems

Q2_2026_TOP_50 = [
    # by value, as SEC's cover pages had it on 2026-10-06 (HD-08's run); 1067983 is Berkshire
    "2012383", "2100119", "93751", "315066", "2100121", "895421", "1214717", "19617", "70858",
    "1446194", "914208", "1595888", "886982", "1374170", "1423053", "73124", "1422849",
    "1610520", "884546", "1422848", "1000275", "72971", "1390777", "902219", "354204", "861177",
    "312069", "820027", "1562230", "764068", "38777", "933478", "1403438", "1407543", "1871926",
    "1452861", "1330387", "1859606", "720005", "948046", "850529", "1445893", "912938",
    "927971", "831001", "1109448", "1067983", "1166588", "1167557", "1273087",
]  # fmt: skip


def test_the_fifty_largest_are_all_named():
    assert len(set(Q2_2026_TOP_50)) == 50
    assert [cik for cik in Q2_2026_TOP_50 if cik not in FILERS and cik not in PROFILES] == []


def test_every_chinese_name_is_taiwan_s():
    names = [f.zh for f in FILERS.values() if f.zh]
    assert taiwan_usage_problems("zh-TW", names) == []
    # and the mainland's names for them are caught in an article too (D-167)
    problems = taiwan_usage_problems("zh-TW", ["惠靈頓與蒙特利爾銀行、富蘭克林鄧普頓"])
    assert any("威靈頓" in p for p in problems)
    assert any("蒙特婁" in p for p in problems)
    assert any("富蘭克林坦伯頓" in p for p in problems)


def test_the_ten_managers_are_named_as_in_institutional_views():
    zh = {f.zh for f in FILERS.values()}
    for institution in INSTITUTIONS:
        chinese = next(n for n in institution.names if not n.isascii())
        assert chinese in zh or any(chinese in name for name in zh if name), institution.key
    assert FILERS["2012383"].zh == "貝萊德" and FILERS["1330387"].zh == "東方匯理"


def test_each_filer_has_a_name_of_its_own():
    for names in ([f.en for f in FILERS.values()], [f.zh for f in FILERS.values() if f.zh]):
        assert len(names) == len(set(names))
    assert all(cik.isdigit() and not cik.startswith("0") for cik in FILERS)
    assert not set(FILERS) & set(PROFILES)  # a followed filer is named by its profile


def test_an_institution_filing_as_several_is_one_group():
    groups: dict[str, list[str]] = {}
    for f in FILERS.values():
        if f.group:
            groups.setdefault(f.group, []).append(f.zh or f.en)
    assert sorted(groups) == ["capital", "trowe", "ubs", "vanguard"]
    assert len(groups["vanguard"]) == 6 and all(n.startswith("先鋒") for n in groups["vanguard"])
    assert all(n.startswith("資本集團") for n in groups["capital"])


def test_the_site_names_a_filer_by_profile_then_table_then_as_filed():
    # a followed filer: as on its card
    assert filer_name("0001067983", "Berkshire Hathaway Inc", "zh-TW") == "波克夏海瑟威"
    assert filer_name("1350694", "Bridgewater Associates, LP", "en") == "Bridgewater Associates"
    # the table, in either language; English on a Chinese page when Taiwan writes it so
    assert filer_name("80255", "PRICE T ROWE ASSOCIATES INC /MD/", "zh-TW") == "普徠仕"
    assert filer_name("80255", "PRICE T ROWE ASSOCIATES INC /MD/", "en") == "T. Rowe Price"
    assert filer_name("1214717", "GEODE CAPITAL MANAGEMENT, LLC", "zh-TW") == (
        "Geode Capital Management"
    )
    # anybody else: as filed
    assert filer_name("2056819", "Arini Capital Management Ltd", "zh-TW") == (
        "Arini Capital Management Ltd"
    )
