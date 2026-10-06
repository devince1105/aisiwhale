"""Who the 13F filers are, in Taiwan's words (HD-09, D-217): 機構排行's names.

A cover page names its filer as the filer's lawyers do — ``FMR LLC``, ``PRICE T ROWE ASSOCIATES
INC /MD/``, ``DEUTSCHE BANK AG\\`` — so the ranking names the largest by this table: the second
quarter of 2026's top 50 by value, and the few the plan named that file below them or in the
wrong units (T. Rowe Price filed it in thousands).

**Chinese only where Taiwan has a settled name** — 貝萊德, 先鋒, 普徠仕, 威靈頓 (not mainland's
惠靈頓), 聯博, MFS全盛, 城堡投資; a firm Taiwan's press writes in English (Geode, Susquehanna,
Jane Street, Dimensional) keeps its English name on the Chinese page too, rather than one made
up here. The ten 機構觀點 managers' names are ``institutions``'s, so 貝萊德 is written one way
across the site; and every Chinese name passes the writers' check (``taiwan_usage_problems``).

**One institution, several filers**: Vanguard files as five (two since its 2026 split), Capital
Group as three, UBS as two. Each is its own row — they are separate filings — named by the
institution's Taiwan name and which part it is (先鋒資本管理; 資本集團 and the part's own English
name), with a ``group`` to put them together.

The followed filers (``holdings.PROFILES``: Berkshire, Bridgewater…) are named by their
profiles, as on the cards.
"""

from __future__ import annotations

from dataclasses import dataclass

from autora.domains.newsroom.holdings import PROFILES
from autora.domains.newsroom.institutions import INSTITUTIONS


@dataclass(frozen=True)
class Filer:
    en: str
    """As Taiwan's and the filer's own press write it: ``BlackRock``, not ``BlackRock, Inc.``."""
    zh: str | None = None
    """Taiwan's name; None when Taiwan writes it in English."""
    group: str | None = None
    """The institution a filer is part of, when it files as several (``vanguard``)."""

    def name(self, lang: str) -> str:
        return self.zh if self.zh and lang.lower().startswith("zh") else self.en


def _zh(key: str) -> str:
    """A 機構觀點 manager's Chinese name (``institutions``): the first of its names in Chinese."""
    institution = next(i for i in INSTITUTIONS if i.key == key)
    return next(n for n in institution.names if not n.isascii())


FILERS: dict[str, Filer] = {
    # the second quarter of 2026's 50 largest, in order (Berkshire is a profile)
    "2012383": Filer("BlackRock", _zh("blackrock")),
    "2100119": Filer("Vanguard Capital Management", "先鋒資本管理", "vanguard"),
    "93751": Filer("State Street", _zh("state_street")),
    "315066": Filer("Fidelity (FMR)", _zh("fidelity")),
    "2100121": Filer("Vanguard Portfolio Management", "先鋒投資組合管理", "vanguard"),
    "895421": Filer("Morgan Stanley", "摩根士丹利"),
    "1214717": Filer("Geode Capital Management"),
    "19617": Filer("JPMorgan Chase", _zh("jpmorgan")),
    "70858": Filer("Bank of America", "美國銀行"),
    "1446194": Filer("Susquehanna International Group"),
    "914208": Filer("Invesco", "景順"),
    "1595888": Filer("Jane Street"),
    "886982": Filer("Goldman Sachs", _zh("goldman")),
    "1374170": Filer("Norges Bank", "挪威央行"),
    "1423053": Filer("Citadel Advisors", "城堡投資"),
    "73124": Filer("Northern Trust", "北方信託"),
    "1422849": Filer("Capital World Investors", "資本集團（Capital World Investors）", "capital"),
    "1610520": Filer("UBS Group", "瑞銀集團", "ubs"),
    "884546": Filer("Charles Schwab Investment Management", "嘉信理財"),
    "1422848": Filer(
        "Capital Research Global Investors",
        "資本集團（Capital Research Global Investors）",
        "capital",
    ),
    "1000275": Filer("Royal Bank of Canada", "加拿大皇家銀行"),
    "72971": Filer("Wells Fargo", "富國銀行"),
    "1390777": Filer("BNY", _zh("bny")),
    "902219": Filer("Wellington Management", "威靈頓"),
    "354204": Filer("Dimensional Fund Advisors"),
    "861177": Filer("UBS Asset Management", "瑞銀資產管理", "ubs"),
    "312069": Filer("Barclays", "巴克萊"),
    "820027": Filer("Ameriprise Financial"),
    "1562230": Filer(
        "Capital International Investors", "資本集團（Capital International Investors）", "capital"
    ),
    "764068": Filer("Legal & General"),
    "38777": Filer("Franklin Templeton (Franklin Resources)", "富蘭克林坦伯頓"),
    "933478": Filer("Vanguard Fiduciary Trust", "先鋒信託", "vanguard"),
    "1403438": Filer("LPL Financial"),
    "1407543": Filer("Envestnet"),
    "1871926": Filer("Nuveen"),
    "1452861": Filer("IMC"),
    "1330387": Filer("Amundi", _zh("amundi")),
    "1859606": Filer("Optiver"),
    "720005": Filer("Raymond James"),
    "948046": Filer("Deutsche Bank", "德意志銀行"),
    "850529": Filer("Fisher Investments"),
    "1445893": Filer("CTC (Chicago Trading Company)"),
    "912938": Filer("MFS Investment Management", "MFS全盛"),
    "927971": Filer("BMO (Bank of Montreal)", "蒙特婁銀行"),
    "831001": Filer("Citigroup", "花旗集團"),
    "1109448": Filer("AllianceBernstein", "聯博"),
    "1166588": Filer("BNP Paribas", "法國巴黎銀行"),
    "1167557": Filer("AQR Capital Management"),
    "1273087": Filer("Millennium Management"),
    # the rest of Vanguard, and well-known names below the top 50 (or, T. Rowe Price, filed in
    # thousands of dollars: about US$1 trillion, not 1 billion)
    "1811242": Filer("Vanguard Global Advisers", "先鋒全球顧問", "vanguard"),
    "1680208": Filer("Vanguard Asset Management (UK)", "先鋒資產管理（英國）", "vanguard"),
    "102909": Filer("Vanguard Group", "先鋒集團", "vanguard"),
    "80255": Filer("T. Rowe Price", "普徠仕"),
    "1037389": Filer("Renaissance Technologies", "文藝復興科技"),
    "1179392": Filer("Two Sigma Investments"),
    "873630": Filer("HSBC", "匯豐"),
    "1582202": Filer("Swiss National Bank", "瑞士央行"),
    "1283718": Filer("Canada Pension Plan Investment Board", "加拿大退休金計畫投資委員會"),
    "919079": Filer("CalPERS", "加州公務員退休基金"),
    "1466546": Filer("Mitsubishi UFJ Asset Management", "三菱日聯資產管理"),
    "1475365": Filer("Sumitomo Mitsui Trust", "三井住友信託"),
    "1608046": Filer("National Pension Service (Korea)", "韓國國民年金"),
    "1465109": Filer("Neuberger Berman", "路博邁"),
    "1086619": Filer("Schroders", "施羅德"),
    "1088875": Filer("Baillie Gifford", "柏基"),
}


def filer_name(cik: str, filed: str, lang: str) -> str:
    """How the site names a 13F filer in ``lang``: its profile's filer (the cards' name for it),
    this table's, or — for the thousands of others — the name it filed under."""
    cik = cik.lstrip("0")
    profile = PROFILES.get(cik)
    if profile is not None:
        return profile.entity(lang)
    known = FILERS.get(cik)
    return known.name(lang) if known is not None else filed
