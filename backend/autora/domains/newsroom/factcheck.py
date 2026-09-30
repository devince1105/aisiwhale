"""Deterministic fact-check (T-510, platform/05 §3 layers 1 and 2). No language model decides
anything here; layer 3 (does the quote really support the claim?) is the editor's, and the
report lists what it has to judge.

**Layer 1, structure** (fact, number and quote claims):
- at least one ``supports`` quote;
- every quote is still the evidence's own text at its recorded place;
- low-trust sources cannot support a claim alone: at least one supporting source must reach
  ``min_trust``, or two independent sources (different sources or sites) must agree;
- a **number** claim's numbers each appear in a supporting quote, compared as values with their
  scale words: "NT$420 million" matches "4.2 億", "3,000" matches "3000", "18%" matches "18 %".
  Also as the source wrote them (D-137): in words ("eight" is 8, 五 is 5), as a month's name
  ("April" is 4, "Feb." is 2), in a table whose cells ran together ("Euro0.8822"), or rounded
  (0.8822 for 0.882222768). And a date the claim names — its year, month and day, which D-083
  requires — may come from when the source was published or retrieved, or the day before it
  ("昨日", "yesterday"): only the parts of a date, never a count or an amount.

**Layer 2, cross-check**:
- a fact, number or quote claim with a ``contradicts`` quote fails: a contested point must be
  written as who said what (an ``attribution`` claim), which may carry contradictions;
- other passages of the story's evidence that are close to the claim (vector search) are listed
  for the editor: advisory, they do not decide the verdict.

Opinions need no evidence; attributions need no support rule beyond having some quote.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from urllib.parse import urlsplit

from autora.domains.newsroom.models import ClaimType, SupportType

CHECKED = {ClaimType.FACT, ClaimType.NUMBER, ClaimType.QUOTE}

_SCALE = {
    "thousand": 1e3,
    "million": 1e6,
    "millions": 1e6,
    "billion": 1e9,
    "billions": 1e9,
    "trillion": 1e12,
    "千": 1e3,
    "萬": 1e4,
    "万": 1e4,
    "億": 1e8,
    "亿": 1e8,
    "兆": 1e12,
}
_NUMBER = re.compile(
    r"(?<![A-Za-z0-9.])(\d{1,3}(?:,\d{3})+|\d+)(\.\d+)?\s*"
    r"(thousand|millions?|billions?|trillion|千|萬|万|億|亿|兆)?",
    re.IGNORECASE,
)


def numbers(text: str) -> list[float]:
    """The numbers in ``text`` as values, scale words applied (``4.2 億`` -> 420000000.0)."""
    values = []
    for whole, fraction, scale in _NUMBER.findall(text):
        value = float(whole.replace(",", "") + (fraction or ""))
        values.append(value * _SCALE.get(scale.lower(), 1.0) if scale else value)
    return values


def _same(a: float, b: float) -> bool:
    return math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-9)


# --- numbers as a source may write them (D-137) ----------------------------------------------

# a number glued to the letters before it: a table's cells run together ("Euro0.8822")
_GLUED = re.compile(
    r"(?<![0-9.])(\d{1,3}(?:,\d{3})+|\d+)(\.\d+)?\s*"
    r"(thousand|millions?|billions?|trillion|千|萬|万|億|亿|兆)?",
    re.IGNORECASE,
)
_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
    "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70,
    "eighty": 80, "ninety": 90, "dozen": 12,
}  # fmt: skip
_WORD = re.compile(
    r"\b(" + "|".join(_WORDS) + r")(?:-(one|two|three|four|five|six|seven|eight|nine))?\b",
    re.IGNORECASE,
)
_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7, "aug": 8, "sep": 9,
    "oct": 10, "nov": 11, "dec": 12,
}  # fmt: skip
_MONTH = re.compile(
    r"\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?"
    r"|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\b\.?",
    re.IGNORECASE,
)
_CN_DIGITS = {
    "零": 0,
    "〇": 0,
    "一": 1,
    "二": 2,
    "兩": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}
_CN = re.compile(r"[零〇一二兩两三四五六七八九十百]{1,5}")


def _chinese(run: str) -> int | None:
    """一 → 1, 十五 → 15, 二十 → 20, 三百零五 → 305; None for what is not a number."""
    total, current = 0, 0
    for ch in run:
        if ch in _CN_DIGITS:
            current = _CN_DIGITS[ch]
        elif ch == "十":
            total += (current or 1) * 10
            current = 0
        elif ch == "百":
            total += (current or 1) * 100
            current = 0
    value = total + current
    return value if value or "零" in run or "〇" in run else None


def quote_numbers(text: str) -> list[float]:
    """Every number a quote states, however it states it (see the module's note)."""
    values = numbers(text)
    for whole, fraction, scale in _GLUED.findall(text):
        value = float(whole.replace(",", "") + (fraction or ""))
        values.append(value * _SCALE.get(scale.lower(), 1.0) if scale else value)
    for word, unit in _WORD.findall(text):
        values.append(float(_WORDS[word.lower()] + (_WORDS[unit.lower()] if unit else 0)))
    values += [float(_MONTHS[m.lower()[:3]]) for m in _MONTH.findall(text)]
    values += [float(v) for run in _CN.findall(text) if (v := _chinese(run)) is not None]
    return values


def claim_numbers(text: str) -> list[tuple[float, int]]:
    """A claim's numbers, each with its decimal places (a rounded figure matches its source)."""
    out = []
    for whole, fraction, scale in _NUMBER.findall(text):
        value = float(whole.replace(",", "") + (fraction or ""))
        places = len(fraction) - 1 if fraction and not scale else 0
        out.append((value * _SCALE.get(scale.lower(), 1.0) if scale else value, places))
    return out


_DATE_PARTS = re.compile(
    r"(\d{4})\s*年|(\d{1,2})\s*月|(\d{1,2})\s*日|(?<!\d)((?:19|20)\d{2})(?!\d)"
    r"|(\d{4})-(\d{1,2})-(\d{1,2})"
)
_EN_DATE = re.compile(
    r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(\d{1,2})(?:,\s*(\d{4}))?",
    re.IGNORECASE,
)


def claim_date_parts(text: str) -> set[float]:
    """The numbers of the dates a claim names: its years, months and days."""
    parts = {float(n) for groups in _DATE_PARTS.findall(text) for n in groups if n}
    parts |= {float(n) for groups in _EN_DATE.findall(text) for n in groups if n}
    return parts


def dated(dates: tuple[date, ...]) -> set[float]:
    """The year, month and day of each date, and of the day before it (a source's 'yesterday')."""
    parts: set[float] = set()
    for d in dates:
        for day in (d, d - timedelta(days=1)):
            parts |= {float(day.year), float(day.month), float(day.day)}
    return parts


@dataclass(frozen=True)
class QuoteFacts:
    evidence_id: str
    quote: str
    support_type: str
    intact: bool
    """The quote is still the evidence's text at its recorded offsets."""
    trust: Decimal
    source_key: str
    """Who vouches for it: the source, or the page's site when no source listed it."""
    dates: tuple[date, ...] = ()
    """When the source was published and when it was retrieved (D-137): what "昨日" or a year
    the quote leaves out is counted from."""


def source_key(source_id: object | None, url: str) -> str:
    return f"source:{source_id}" if source_id else f"site:{urlsplit(url).hostname or url}"


@dataclass
class ClaimVerdict:
    claim_id: str
    claim_type: str
    passed: bool = True
    problems: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def fail(self, problem: str) -> None:
        self.passed = False
        self.problems.append(problem)


def check_claim(
    claim_id: str,
    claim_type: str,
    text: str,
    quotes: list[QuoteFacts],
    *,
    min_trust: Decimal,
) -> ClaimVerdict:
    verdict = ClaimVerdict(claim_id=claim_id, claim_type=claim_type)
    kind = ClaimType(claim_type)
    broken = [q for q in quotes if not q.intact]
    for q in broken:
        verdict.fail(f"a quote no longer matches evidence {q.evidence_id} at its place")
    supports = [q for q in quotes if q.intact and q.support_type == SupportType.SUPPORTS]
    contradicts = [q for q in quotes if q.intact and q.support_type == SupportType.CONTRADICTS]

    if kind in CHECKED:
        if not supports:
            verdict.fail("no supporting quote")
        else:
            trusted = [q for q in supports if q.trust >= min_trust]
            independent = {q.source_key for q in supports}
            if not trusted and len(independent) < 2:
                verdict.fail(
                    f"only low-trust support (below {min_trust}) from one source: "
                    "add a trusted source or a second independent one"
                )
        if kind is ClaimType.NUMBER:
            quoted = [n for q in supports for n in quote_numbers(q.quote)]
            date_parts = claim_date_parts(text)
            when = dated(tuple(d for q in supports for d in q.dates))
            for value, places in claim_numbers(text):
                if any(
                    _same(value, n) or (places and _same(round(n, places), value)) for n in quoted
                ):
                    continue
                if value in date_parts and value in when:
                    continue  # a date's part, from when the source was published
                shown = f"{value:g}"
                verdict.fail(f"the number {shown} is not in any supporting quote")
        if contradicts:
            verdict.fail(
                f"contradicted by evidence {sorted({q.evidence_id for q in contradicts})}: "
                "write the contested point as who said what (an attribution claim)"
            )
    else:
        if contradicts:
            verdict.notes.append("contradicting evidence is reported with the attribution")
        if kind is ClaimType.ATTRIBUTION and not quotes:
            verdict.fail("an attribution needs a quote showing who said or did it")
    return verdict
