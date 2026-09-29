"""What the two languages must agree on, and what the Chinese must not leave in English (D-130).

After the vague periods D-083 refuses, the editor's next most frequent reason to send a draft
back (2026-09: 33 "translation" issues across 26 stories, about one story in three) was one of
two things a rule can see as well as an editor can:

- **English left in the Chinese prose**: "75.35 million XRP", "取得更多 traction". Rule 12 of the
  writer's brief already says the Chinese writes Chinese units and no English words; nothing
  held it to that. A name is not a word left untranslated (Microsoft, AI for Good Lab, Harbor
  District: a run of English that begins and ends with a capital), nor is anything quoted
  or glossed — in 「」, 『』, 《》, “”, or brackets (吸引力（traction）) — nor a quote block.
  What is left is a lowercase English word in the writer's own Chinese sentence.
- **The languages disagreeing on a year or a percentage**: a paragraph whose English says 2026
  and whose Chinese says no year (or 2025), or 4.5% against 4%. Checked paragraph by paragraph,
  when both versions have the same blocks in the same order (a writer who restructures one
  language is not second-guessed here; the editor still reads it).
- **An amount converted at the wrong scale**: 外資賣超338億元 written "NT$338 billion" (it is
  33.8 billion). Only a factor of ten, a hundred or a thousand is called out — an amount one
  language gives and the other leaves out is the editor's to weigh, not a rule's.

``language.script_problems`` deliberately checks only the title and summary; this does not
change that — English quoted at length in the body is still allowed, as long as it is quoted.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

from autora.domains.newsroom.language import wants_han

QUOTED = re.compile(r"「[^」]*」|『[^』]*』|《[^》]*》|“[^”]*”|\"[^\"]*\"|（[^）]*）|\([^)]*\)")
LATIN_RUN = re.compile(r"[A-Za-z][A-Za-z0-9.'&-]*(?:[  ]+[A-Za-z0-9][A-Za-z0-9.'&-]*)*")
URL = re.compile(r"https?://\S+")
MIN_WORD = 3

YEAR = re.compile(r"(?<!\d)(?:19|20)\d{2}(?!\d)")
PERCENT = re.compile(r"(\d+(?:\.\d+)?)\s*(?:%|％|percent\b|per cent\b)", re.IGNORECASE)


def _untranslated(text: str) -> list[str]:
    """Lowercase English words in the writer's own Chinese (not a name, not quoted)."""
    words: list[str] = []
    for run in LATIN_RUN.findall(QUOTED.sub(" ", URL.sub(" ", text))):
        parts = run.split()
        if parts[0][0].isupper() and parts[-1][0].isupper():
            continue  # a name: Microsoft, AI for Good Lab, Harbor District
        words += [p for p in parts if len(p) >= MIN_WORD and p.isalpha() and p.islower()]
    return words


def untranslated_problems(versions: Iterable[Any]) -> list[str]:
    """Every place a Chinese version leaves English words in its own sentences."""
    issues: list[str] = []
    for version in versions:
        if not wants_han(version.lang):
            continue
        places = [(field, getattr(version, field) or "") for field in ("title", "summary")]
        places += [
            (f"block {index} ({block.type})", block.text)
            for index, block in enumerate(version.blocks, 1)
            if block.type != "quote"  # what somebody said, they said
        ]
        for where, text in places:
            if words := _untranslated(text):
                shown = ", ".join(dict.fromkeys(words))
                issues.append(
                    f"{version.lang} {where}: English left in the Chinese text ({shown}); write "
                    "it in Chinese (7,535萬, 1.57億美元, 吸引力), or quote it in 「」 if it is a "
                    "title or somebody's words"
                )
    return issues


ZH_AMOUNT = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*(兆|億|萬)")
EN_AMOUNT = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*(trillion|billion|million)\b", re.IGNORECASE)
ZH_SCALE = {"兆": 1e12, "億": 1e8, "萬": 1e4}
EN_SCALE = {"trillion": 1e12, "billion": 1e9, "million": 1e6}
SCALE_SLIPS = (10.0, 100.0, 1000.0)


def _amounts(
    pattern: re.Pattern[str], scale: dict[str, float], text: str
) -> list[tuple[str, float]]:
    return [
        (
            f"{number}{'' if unit in ZH_SCALE else ' '}{unit}",
            float(number.replace(",", "")) * scale[unit.lower()],
        )
        for number, unit in pattern.findall(text)
    ]


def _close(a: float, b: float) -> bool:
    return abs(a - b) <= 0.01 * max(abs(a), abs(b))


def _scale_slips(zh_text: str, other_text: str) -> list[str]:
    """Amounts one language gives ten, a hundred or a thousand times the other's."""
    zh = _amounts(ZH_AMOUNT, ZH_SCALE, zh_text)
    other = _amounts(EN_AMOUNT, EN_SCALE, other_text)
    slips = []
    for said, value in other:
        if any(_close(value, v) for _, v in zh):
            continue
        for written, v in zh:
            if any(_close(value, v * f) or _close(value * f, v) for f in SCALE_SLIPS):
                slips.append(f"{written} is not {said}")
    return slips


def _numbers(text: str) -> tuple[set[str], set[str]]:
    return set(YEAR.findall(text)), {p.rstrip("0").rstrip(".") for p in PERCENT.findall(text)}


def mismatch_problems(versions: list[Any]) -> list[str]:
    """Paragraphs whose Chinese and English give different years or percentages."""
    han = [v for v in versions if wants_han(v.lang)]
    other = [v for v in versions if not wants_han(v.lang)]
    issues: list[str] = []
    for zh in han:
        for version in other:
            if [b.type for b in zh.blocks] != [b.type for b in version.blocks]:
                continue  # not aligned block by block: the editor reads it
            for index, (a, b) in enumerate(zip(zh.blocks, version.blocks, strict=True), 1):
                if a.type == "quote":
                    continue
                (years_a, pct_a), (years_b, pct_b) = _numbers(a.text), _numbers(b.text)
                for slip in _scale_slips(a.text, b.text):
                    issues.append(
                        f"block {index}: {slip} ({zh.lang} against {version.lang}); convert the "
                        "unit, don't copy it: 338億元 is NT$33.8 billion, 7,535萬 is 75.35 million"
                    )
                for what, left, right in (
                    ("years", years_a, years_b),
                    ("percentages", pct_a, pct_b),
                ):
                    if left != right:
                        issues.append(
                            f"block {index}: the {what} differ between {zh.lang} "
                            f"({', '.join(sorted(left)) or 'none'}) and {version.lang} "
                            f"({', '.join(sorted(right)) or 'none'}); both languages say the same"
                        )
    return issues
