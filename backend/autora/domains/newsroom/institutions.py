"""The asset managers 機構觀點 reports on, and the rule that keeps their views theirs (D-058).

An institution's view is only its view if it came from the institution. The first two articles
of the section broke that the same way: the Fidelity piece ended with a figure from a Vanguard
article, written as "another Fidelity estimate"; the fact-check passed it, because the number
matched its quote — it checks what a source says, not who the article says it is. So a draft of
a 機構觀點 story is also checked here: every paragraph must name the institution whose view it
reports, and every claim it cites must rest on evidence from that institution's own site.

The same list gives the section's searches their sites (``markets.py``), so a firm added here is
searched and checked alike.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

SECTION = "institutions"


@dataclass(frozen=True)
class Institution:
    key: str
    names: tuple[str, ...]
    """How an article may name it, in Chinese and English."""
    domains: tuple[str, ...]
    """Its own sites: a page on one of them, or on a subdomain, is the institution speaking."""


INSTITUTIONS: tuple[Institution, ...] = (
    Institution("blackrock", ("貝萊德", "BlackRock"), ("blackrock.com",)),
    Institution("vanguard", ("先鋒", "Vanguard"), ("vanguard.com",)),
    Institution("fidelity", ("富達", "Fidelity"), ("fidelity.com", "fidelityinstitutional.com")),
    Institution("ubs", ("瑞銀", "UBS"), ("ubs.com",)),
    Institution("state_street", ("道富", "State Street", "SSGA"), ("ssga.com", "statestreet.com")),
    Institution(
        "jpmorgan", ("摩根大通", "小摩", "J.P. Morgan", "JPMorgan", "JP Morgan"), ("jpmorgan.com",)
    ),
    Institution("goldman", ("高盛", "Goldman Sachs"), ("goldmansachs.com", "gsam.com")),
    Institution("capital_group", ("資本集團", "Capital Group"), ("capitalgroup.com",)),
    Institution(
        "amundi", ("Amundi", "東方匯理", "法國農業信貸", "Crédit Agricole"), ("amundi.com",)
    ),
    Institution("bny", ("紐約梅隆", "BNY"), ("bny.com",)),
)
"""The ten largest asset managers (D-057). Crédit Agricole's asset manager is Amundi."""


def _pattern(name: str) -> re.Pattern[str]:
    # a Latin name is a whole word, any case ("UBS" is not in "subsidy"); a Chinese one is text
    if name.isascii():
        return re.compile(rf"(?<![A-Za-z]){re.escape(name)}(?![A-Za-z])", re.IGNORECASE)
    return re.compile(re.escape(name))


_PATTERNS = [(i, [_pattern(n) for n in i.names]) for i in INSTITUTIONS]


def named_in(text: str) -> list[Institution]:
    """The institutions a sentence names."""
    return [i for i, patterns in _PATTERNS if any(p.search(text) for p in patterns)]


def speaks_for(url: str, institution: Institution) -> bool:
    host = (urlsplit(url).hostname or "").lower()
    return any(host == d or host.endswith("." + d) for d in institution.domains)


def domains(*keys: str) -> tuple[str, ...]:
    """The sites of these institutions, in order: what the section's searches look at."""
    by_key = {i.key: i for i in INSTITUTIONS}
    return tuple(d for key in keys for d in by_key[key].domains)


def attribution_problems(
    versions: Iterable[Any], sources: Mapping[uuid.UUID, set[str]]
) -> list[str]:
    """Every paragraph of a 機構觀點 draft that reports a view without its institution's word.

    ``versions``: the draft's ``LanguageVersion``s. ``sources``: each cited claim's evidence
    URLs (claims that do not exist are the caller's problem)."""
    issues: list[str] = []
    for version in versions:
        for number, block in enumerate(version.blocks, start=1):
            if block.type == "heading" or not block.claim_ids:
                continue
            named = named_in(block.text)
            where = f"{version.lang} block {number}"
            if not named:
                issues.append(
                    f"{where}: a 機構觀點 paragraph says whose view it is — name the institution "
                    "(貝萊德, 富達, 摩根大通…) whose publication it reports"
                )
                continue
            for claim_id in block.claim_ids:
                urls = sources.get(claim_id, set())
                if not any(speaks_for(u, i) for u in urls for i in named):
                    hosts = sorted({urlsplit(u).hostname or u for u in urls}) or ["no evidence"]
                    names = "、".join(i.names[0] for i in named)
                    issues.append(
                        f"{where}: claim {claim_id} comes from {', '.join(hosts)}, not from "
                        f"{names}'s own site — a view is only {names}'s if {names} published it. "
                        "Drop the claim, or leave the other source out of this article"
                    )
    return issues
