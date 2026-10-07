"""機構排行 and an institution's page, as the site shows them (HD-11, D-217).

**The ranking** is every 13F filer's quarter (``thirteenf_index``), largest first, in dollars,
named as Taiwan writes them (``filers``), with how much its holdings' value changed against the
quarter before — prices included: the change in what it holds, not what it bought, which only
an institution's page estimates. The quarter shown is the latest whose 13Fs were all due
(``ranked_period``), so that half the filers are not missing from it; earlier ones with enough
filers read can be asked for. Two quarters' totals are some 20,000 filings, so they are worked
out once every ``CACHE_SECONDS`` (the index is read every ten minutes anyway).

**An institution's page** is its quarter's numbers and what ``institution_details`` worked out:
the largest holdings — the first ``FREE_TOP`` for anybody, all of them signed in (free, D-159) —
and, signed in, the biggest buys and sells. One that has not been worked out is queued the first
time somebody opens it; the page says to come back in a few minutes.

Nothing here knows who is reading: the API says whether they are signed in.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any, Literal

from pydantic import BaseModel
from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from autora.domains.newsroom import cusips, institution_details, thirteenf, thirteenf_index
from autora.domains.newsroom.filers import FILERS, filer_name
from autora.domains.newsroom.holdings import PROFILES
from autora.domains.newsroom.models import InstitutionDetail, ThirteenFFiling
from autora.domains.newsroom.portfolios import _shown

CACHE_SECONDS = 600.0
MIN_FILERS = 1000
"""A quarter with fewer filers read is not offered: late amendments to old quarters, or one
still being read."""
PAGE = 50
FREE_TOP = 10
Sort = Literal["value", "change", "filed"]


# --- the ranking ---------------------------------------------------------------------------------


class PublicRankRow(BaseModel):
    rank: int
    """By value, among all the quarter's filers (a search keeps it)."""
    cik: str
    name: str
    """Taiwan's name for it (貝萊德), its English one, or the name it filed under."""
    filed_name: str
    value_usd: int
    previous_value_usd: int | None
    change_usd: int | None
    """Against the quarter before: what it holds is worth more or less, its trades and the
    market together. None when it did not file that quarter."""
    change_pct: float | None
    entries: int
    filed: date
    in_thousands: bool
    """Filed in thousands of dollars (against the rule since 2023), multiplied here."""
    in_doubt: bool
    """May be in thousands; not checked yet."""
    group: str | None
    """The institution it is part of when it files as several (``vanguard``)."""
    profile: str | None
    """The followed filer's page (``buffett``), when it has one."""


class PublicRanking(BaseModel):
    period: date
    previous_period: date | None
    """The quarter compared with; None when it is not known."""
    periods: list[date]
    """Every quarter that can be asked for, latest first."""
    filers: int
    total: int
    """Rows matching the search."""
    rows: list[PublicRankRow]


@dataclass
class _Kept:
    at: float
    totals: list[thirteenf_index.Total]


_kept: dict[date, _Kept] = {}


def forget() -> None:
    """Drop the totals kept (a test's database is not the last one's)."""
    _kept.clear()


async def _totals(session: AsyncSession, period: date) -> list[thirteenf_index.Total]:
    now = time.monotonic()
    kept = _kept.get(period)
    if kept is None or now - kept.at > CACHE_SECONDS:
        kept = _Kept(now, await thirteenf_index.quarter_totals(session, period))
        _kept[period] = kept
    return kept.totals


async def periods(session: AsyncSession, *, today: date | None = None) -> list[date]:
    """The quarters a ranking can show: read for ``MIN_FILERS`` filers or more, and all due."""
    latest = thirteenf_index.ranked_period(today or datetime.now(UTC).date())
    rows = await session.execute(
        select(ThirteenFFiling.period)
        .where(ThirteenFFiling.read_at.is_not(None), ThirteenFFiling.period <= latest)
        .group_by(ThirteenFFiling.period)
        .having(func.count(distinct(ThirteenFFiling.cik)) >= MIN_FILERS)
        .order_by(ThirteenFFiling.period.desc())
    )
    return list(rows.scalars().all())


def _profile(cik: str) -> str | None:
    profile = PROFILES.get(cik)
    return profile.slug if profile is not None else None


def _rows(
    now: list[thirteenf_index.Total], before: list[thirteenf_index.Total], lang: str
) -> list[PublicRankRow]:
    earlier = {t.cik: t for t in before}
    out = []
    for rank, t in enumerate(now, start=1):
        prev = earlier.get(t.cik)
        change = t.value_usd - prev.value_usd if prev is not None else None
        known = FILERS.get(t.cik)
        out.append(
            PublicRankRow(
                rank=rank,
                cik=t.cik,
                name=filer_name(t.cik, t.manager, lang),
                filed_name=t.manager,
                value_usd=t.value_usd,
                previous_value_usd=prev.value_usd if prev is not None else None,
                change_usd=change,
                change_pct=(
                    round(change / prev.value_usd * 100, 2)
                    if prev is not None and change is not None and prev.value_usd
                    else None
                ),
                entries=t.entries,
                filed=t.filed,
                in_thousands=t.in_thousands,
                in_doubt=t.in_doubt,
                group=known.group if known is not None else None,
                profile=_profile(t.cik),
            )
        )
    return out


def _matches(row: PublicRankRow, words: list[str]) -> bool:
    text = f"{row.name} {row.filed_name} {row.cik}".casefold()
    return all(word in text for word in words)


def _sorted(rows: list[PublicRankRow], sort: Sort, ascending: bool) -> list[PublicRankRow]:
    """Largest first (or smallest, ``ascending``); a filer with no change to sort by last
    either way."""
    sign = 1 if ascending else -1
    if sort == "change":
        return sorted(
            rows,
            key=lambda r: (r.change_usd is None, sign * (r.change_usd or 0), r.rank),
        )
    if sort == "filed":
        return sorted(rows, key=lambda r: (sign * r.filed.toordinal(), r.rank))
    return sorted(rows, key=lambda r: -sign * r.rank)


async def ranking(
    session: AsyncSession,
    *,
    lang: str,
    period: date | None = None,
    q: str | None = None,
    sort: Sort = "value",
    ascending: bool = False,
    limit: int = PAGE,
    offset: int = 0,
    today: date | None = None,
) -> PublicRanking:
    """A quarter's ranking: searched (every word of ``q`` in the name, the filed name or the
    CIK), sorted, a page of it. A quarter not offered is the default one."""
    offered = await periods(session, today=today)
    default = offered[0] if offered else thirteenf_index.ranked_period(today or date.today())
    period = period if period in offered else default
    earlier = thirteenf_index.previous_period(period)
    now, before = await _totals(session, period), await _totals(session, earlier)
    rows = _rows(now, before, lang)
    words = (q or "").casefold().split()
    if words:
        rows = [r for r in rows if _matches(r, words)]
    rows = _sorted(rows, sort, ascending)
    return PublicRanking(
        period=period,
        previous_period=earlier if before else None,
        periods=offered,
        filers=len(now),
        total=len(rows),
        rows=rows[offset : offset + limit],
    )


# --- an institution ------------------------------------------------------------------------------


class PublicInstitutionHolding(BaseModel):
    symbol: str | None
    """Its US ticker, when known: the stock's page on the site."""
    name: str
    cusip: str
    title_of_class: str
    change: str | None
    """``new``, ``increased``, ``decreased``, ``sold_out``, ``unchanged``; None with no quarter
    before to compare."""
    shares: int
    previous_shares: int
    value_usd: int
    previous_value_usd: int
    weight_pct: float | None
    traded_usd: int | None
    """Bought (+) or sold (−), estimated at the quarter-end price; None when a corporate action
    (a new CUSIP) leaves it unknown."""
    split: str | None
    """``10:1``: the shares are compared after the split."""


class PublicFiling(BaseModel):
    accession: str
    form: str
    filed: date
    url: str
    in_thousands: bool


class PublicInstitution(BaseModel):
    cik: str
    name: str
    filed_name: str
    group: str | None
    profile: str | None
    period: date
    periods: list[date]
    rank: int | None
    value_usd: int
    previous_value_usd: int | None
    change_usd: int | None
    entries: int
    filed: date
    in_thousands: bool
    in_doubt: bool
    filings: list[PublicFiling]
    status: Literal["ready", "queued", "failed"]
    """``queued``: being worked out, a few minutes after it was first opened."""
    computed_at: datetime | None
    previous_period: date | None
    stock_value_usd: int | None
    previous_stock_value_usd: int | None
    stocks: int | None
    net_bought_usd: int | None
    counts: dict[str, int]
    top: list[PublicInstitutionHolding]
    top_total: int
    """How many of the largest holdings there are to see (up to 50)."""
    bought: list[PublicInstitutionHolding]
    sold: list[PublicInstitutionHolding]
    locked: bool
    """The rest is for a reader signed in."""


async def _holdings(
    session: AsyncSession, rows: list[dict[str, Any]], lang: str
) -> list[PublicInstitutionHolding]:
    tickers = await cusips.symbols(session, [r["cusip"] for r in rows])
    out = []
    for r in rows:
        symbol = tickers.get(r["cusip"])
        out.append(
            PublicInstitutionHolding(
                symbol=symbol,
                name=_shown(symbol, r["name"], lang),
                cusip=r["cusip"],
                title_of_class=r["title_of_class"],
                change=r.get("change"),
                shares=r["shares"],
                previous_shares=r["previous_shares"],
                value_usd=r["value_usd"],
                previous_value_usd=r["previous_value_usd"],
                weight_pct=r.get("weight_pct"),
                traded_usd=r.get("traded_usd"),
                split=r.get("split"),
            )
        )
    return out


async def institution(
    session: AsyncSession,
    cik: str,
    *,
    lang: str,
    signed_in: bool,
    period: date | None = None,
    today: date | None = None,
    now: datetime | None = None,
) -> PublicInstitution | None:
    """A filer's page for a quarter; None when it filed no 13F for it. Its holdings are queued
    to be worked out if nobody has asked before (the caller commits)."""
    cik = cik.lstrip("0")
    offered = await periods(session, today=today)
    default = offered[0] if offered else thirteenf_index.ranked_period(today or date.today())
    period = period if period in offered else default
    filings = await thirteenf_index.quarter_of(session, cik, period)
    if not filings:
        return None
    detail = await session.get(InstitutionDetail, (cik, period))
    if detail is None:
        detail = await institution_details.request(session, cik, period, now=now)
    (total,) = thirteenf_index.totals(filings)
    rank = next(
        (n for n, t in enumerate(await _totals(session, period), start=1) if t.cik == cik), None
    )
    earlier = thirteenf_index.previous_period(period)
    before = thirteenf_index.totals(await thirteenf_index.quarter_of(session, cik, earlier))
    previous = before[0].value_usd if before else None
    ready = detail.status == "ready"
    top = await _holdings(session, detail.top if ready else [], lang)
    return PublicInstitution(
        cik=cik,
        name=filer_name(cik, total.manager, lang),
        filed_name=total.manager,
        group=FILERS[cik].group if cik in FILERS else None,
        profile=_profile(cik),
        period=period,
        periods=offered,
        rank=rank,
        value_usd=total.value_usd,
        previous_value_usd=previous,
        change_usd=total.value_usd - previous if previous is not None else None,
        entries=total.entries,
        filed=total.filed,
        in_thousands=total.in_thousands,
        in_doubt=total.in_doubt,
        filings=[
            PublicFiling(
                accession=f.accession,
                form=f.form,
                filed=f.filed,
                url=thirteenf.FilingRef(cik=f.cik, accession=f.accession).index_url,
                in_thousands=f.scale == 1000,
            )
            for f in filings
        ],
        status=detail.status,
        computed_at=detail.computed_at,
        previous_period=detail.previous_period,
        stock_value_usd=int(detail.stock_value_usd) if detail.stock_value_usd is not None else None,
        previous_stock_value_usd=(
            int(detail.previous_stock_value_usd)
            if detail.previous_stock_value_usd is not None
            else None
        ),
        stocks=detail.stocks,
        net_bought_usd=int(detail.net_bought_usd) if detail.net_bought_usd is not None else None,
        counts=detail.counts or {},
        top=top if signed_in else top[:FREE_TOP],
        top_total=len(top),
        bought=await _holdings(session, detail.bought, lang) if ready and signed_in else [],
        sold=await _holdings(session, detail.sold, lang) if ready and signed_in else [],
        locked=ready and not signed_in,
    )
