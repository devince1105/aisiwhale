"""Time a reader can place (D-083): a draft's own words name the date or period, never 今年, 上週,
近期 or "this year" alone.

The editor's most frequent reason to send a draft back (2026-09: most of 65 "missing context"
issues across 40 stories, and several stories dropped over it) was a period nobody could place a
few months on — 今年迄今, 上週, 近期, 十月二日 with no year — or, the other way, a writer turning a
source's "this year" into a year the evidence never gave. A word list catches the first kind the
moment the draft is written, so the writer fixes it in the same task, not in an editor's round.

A quote block is exempt: what somebody said, they said. Everything else — title, summary,
headings, paragraphs — names its time: the date or period the evidence gives (2026年9月21日當週,
2025年同期), or the source's own date said as such (截至2026年9月底，據該週評), or nothing.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

VAGUE_TIME = re.compile(
    r"今年|去年|明年|前年|上週|本週|下週|上周|本周|下周|上個月|上月|本月|下個月|下月"
    r"|本季|上季|下季|近期|近日|日前|昨天|今天|明天|昨日|今日"
    r"|\b(?:this|last|next) (?:year|week|month|quarter)\b|\brecently\b|\byesterday\b"
    r"|\btoday\b|\btomorrow\b|\byear[- ]to[- ]date\b",
    re.IGNORECASE,
)

HOW = (
    "write the date or period the evidence gives (2026年, 2026年9月21日當週, 較2025年同期), or "
    "the source's own date said as such (截至2026年9月底，據該週評), or leave it out — never a "
    "year the evidence does not give"
)


def vague_time_problems(versions: Iterable[Any]) -> list[str]:
    """Every place a draft's own words leave a period a reader cannot place."""
    issues: list[str] = []
    for version in versions:
        for field in ("title", "summary"):
            if match := VAGUE_TIME.search(getattr(version, field) or ""):
                issues.append(
                    f"{version.lang} {field}: {match.group(0)!r} cannot be placed later; {HOW}"
                )
        for index, block in enumerate(version.blocks, 1):
            if block.type == "quote":
                continue  # what somebody said, they said
            if match := VAGUE_TIME.search(block.text):
                issues.append(
                    f"{version.lang} block {index} ({block.type}): {match.group(0)!r} cannot be "
                    f"placed later; {HOW}"
                )
    return issues
