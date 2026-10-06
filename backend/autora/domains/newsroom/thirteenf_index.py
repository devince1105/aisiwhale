"""Every 13F filer's quarter, from SEC's daily index (HD-08, D-217): the numbers of 機構排行.

A 13F-HR's cover page (``primary_doc.xml``, some 2 KB) says all a ranking needs — whose it is,
which quarter, how many entries and their total value — so the whole market is read without its
tables: SEC's daily index lists each day's filings (``form.YYYYMMDD.idx``; 1,784 13F-HRs on
2026-08-14 alone), and each listed filing's cover page is read once and kept
(``thirteenf_filings``). A filer's own holdings are ``thirteenf``'s, for the few the site follows.

**A quarter's total**, per filer: its latest RESTATEMENT amendment if it filed one, else its
latest original 13F-HR, plus the NEW HOLDINGS amendments filed after it (they add positions the
first one left out). A 13F notice holds nothing (another manager reports the holdings).

**The runs are short**, since a scheduler handler holds up everything else the worker starts:
every ten minutes, ``DAYS_PER_RUN`` days of the index, newest first, then ``SUMMARIES_PER_RUN``
cover pages, the latest filed first, ``CONCURRENCY`` at a time and ``RATE`` a second at most (SEC
allows ten) — under a minute. The first fill, two quarters of some 10,000 filings each, takes a
few shifts; after that a day is a few dozen, and a deadline's last days a thousand or two.

A day with no index is a holiday — unless it is recent, when the index may only be late and is
asked for again.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import re
from collections import defaultdict
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from xml.etree import ElementTree as ET

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from autora.db.models import Schedule
from autora.domains.newsroom import thirteenf
from autora.domains.newsroom.models import ThirteenFFiling, ThirteenFIndexDay
from autora.infra.http import FetchRefused, FetchUnavailable
from autora.runtime.scheduler import Handler

log = logging.getLogger(__name__)

INDEX_SCHEDULE = "newsroom.refresh_13f_index"
INDEX_CRON = "*/10 * * * *"
DAILY_INDEX = "https://www.sec.gov/Archives/edgar/daily-index/{year}/QTR{quarter}/form.{day}.idx"
START = date(2026, 4, 1)
"""The first day read: the first quarter's 13Fs (2026-03-31) were filed from April on, and the
second's change is measured against it."""
DAYS_PER_RUN = 10
SUMMARIES_PER_RUN = 300
CONCURRENCY = 4
RATE = 6.0
"""Requests a second, at most."""
BUDGET = 60.0
"""Seconds a run may start cover pages for: SEC answering slowly makes a run fewer, not longer."""
LATE = timedelta(days=3)
"""A missing index this recent may only be late: asked for again."""
MAX_ATTEMPTS = 3
INSERT_ROWS = 1000
"""Index rows a statement: five parameters each, under the driver's 32,767."""
RESTATEMENT = "RESTATEMENT"
NEW_HOLDINGS = "NEW HOLDINGS"
NOTICE = "13F NOTICE"

_ROW = re.compile(
    r"^(13F-HR(?:/A)?) +(\S.*?) +(\d+) +(\d{8}) +edgar/data/\3/(\d{10}-\d{2}-\d{6})\.txt",
    re.M,
)
"""A row of the fixed-width index: form, company, CIK, date filed and the filing's file — whose
folder repeats the CIK, so a company name ending in digits is not taken for one."""

Fetch = Callable[[str], Awaitable[bytes]]


# --- what SEC says -------------------------------------------------------------------------------


@dataclass(frozen=True)
class Listed:
    form: str
    company: str
    cik: str
    filed: date
    accession: str


def index_url(day: date) -> str:
    return DAILY_INDEX.format(
        year=day.year, quarter=(day.month - 1) // 3 + 1, day=day.strftime("%Y%m%d")
    )


def parse_daily_index(text: str) -> list[Listed]:
    """A day's ``form.idx``: its 13F-HRs and their amendments (13F-NT, a notice, is another
    form, and left out)."""
    return [
        Listed(
            form=m.group(1),
            company=m.group(2).strip(),
            cik=str(int(m.group(3))),
            filed=datetime.strptime(m.group(4), "%Y%m%d").date(),
            accession=m.group(5),
        )
        for m in _ROW.finditer(text)
    ]


@dataclass(frozen=True)
class Summary:
    period: date
    manager: str
    amendment: str | None
    """``RESTATEMENT`` or ``NEW HOLDINGS`` for an amendment; None for an original."""
    report_type: str
    entries: int
    value_usd: int
    """As filed: in dollars since 2023."""


def _within(root: ET.Element, name: str) -> ET.Element | None:
    """The first element called ``name``, whatever its namespace (they vary with the software
    that filed it)."""
    return next((e for e in root.iter() if thirteenf._local(e.tag) == name), None)


def _text(root: ET.Element | None, name: str) -> str:
    return thirteenf._child_text(root, name) if root is not None else ""


def _count(text: str) -> int:
    try:
        return int(text.replace(",", "")) if text else 0
    except ValueError as exc:
        raise thirteenf.FilingError(f"not a number on the summary page: {text[:40]!r}") from exc


def parse_summary(body: bytes) -> Summary:
    """A 13F cover page and its summary page (``primary_doc.xml``). DTDs and entities are
    refused, as in ``thirteenf``."""
    root = thirteenf._parse_xml(body)
    cover = _within(root, "coverPage")
    if cover is None:
        raise thirteenf.FilingError("not a 13F cover page")
    try:
        period = datetime.strptime(_text(cover, "reportCalendarOrQuarter"), "%m-%d-%Y").date()
    except ValueError as exc:
        raise thirteenf.FilingError(f"no quarter on the cover page: {exc}") from exc
    amended = _text(cover, "isAmendment").lower() == "true"
    summary = _within(root, "summaryPage")
    return Summary(
        period=period,
        manager=_text(_within(cover, "filingManager"), "name"),
        amendment=(_text(cover, "amendmentType").upper() or None) if amended else None,
        report_type=_text(cover, "reportType").upper(),
        entries=_count(_text(summary, "tableEntryTotal")),
        value_usd=_count(_text(summary, "tableValueTotal")),
    )


def _folder(cik: str, accession: str) -> str:
    return f"{thirteenf.ARCHIVES}/{cik}/{accession.replace('-', '')}"


async def read_summary(fetch: Fetch, cik: str, accession: str) -> Summary:
    """The filing's cover page: ``primary_doc.xml``, or — filed by software that names it
    otherwise — whichever of the folder's XML files is one."""
    folder = _folder(cik, accession)
    try:
        return parse_summary(await fetch(f"{folder}/primary_doc.xml"))
    except FetchRefused:
        pass
    try:
        items = json.loads(await fetch(f"{folder}/index.json"))["directory"]["item"]
    except (KeyError, TypeError, ValueError) as exc:
        raise thirteenf.FilingError(f"the filing's folder could not be read: {exc}") from exc
    for item in items:
        name = str(item.get("name", ""))
        if name.lower().endswith(".xml") and name != "primary_doc.xml":
            try:
                return parse_summary(await fetch(f"{folder}/{name}"))
            except thirteenf.FilingError:
                continue  # the information table, most likely
    raise thirteenf.FilingError("no cover page in the filing")


# --- the runs ------------------------------------------------------------------------------------


def _weekdays(first: date, last: date) -> list[date]:
    days = (first + timedelta(days=n) for n in range((last - first).days + 1))
    return [d for d in days if d.weekday() < 5]


async def read_index(
    session: AsyncSession,
    fetch: Fetch,
    *,
    today: date,
    limit: int = DAYS_PER_RUN,
    now: datetime | None = None,
) -> int:
    """Up to ``limit`` weekdays not read yet, from yesterday back to ``START``: their 13F filings
    listed. How many were listed. SEC answering slowly ends the run; the next one goes on."""
    now = now or datetime.now(UTC)
    done = set((await session.scalars(select(ThirteenFIndexDay.day))).all())
    todo = [d for d in reversed(_weekdays(START, today - timedelta(days=1))) if d not in done]
    listed = 0
    for day in todo[:limit]:
        note = None
        try:
            body = await fetch(index_url(day))
        except FetchRefused as error:
            if day >= today - LATE:
                continue  # perhaps not out yet: asked again next run
            body, note = b"", str(error)[:500]  # a holiday, as a rule
        except FetchUnavailable as error:
            log.warning("13f index: %s not read (%s); next run", day, error)
            break
        rows = parse_daily_index(body.decode("latin-1"))
        for chunk in range(0, len(rows), INSERT_ROWS):
            await session.execute(
                insert(ThirteenFFiling)
                .values(
                    [
                        {
                            "accession": r.accession,
                            "cik": r.cik,
                            "company": r.company,
                            "form": r.form,
                            "filed": r.filed,
                        }
                        for r in rows[chunk : chunk + INSERT_ROWS]
                    ]
                )
                .on_conflict_do_nothing(index_elements=["accession"])
            )
        await session.execute(
            insert(ThirteenFIndexDay)
            .values(day=day, listed=len(rows), read_at=now, note=note)
            .on_conflict_do_nothing(index_elements=["day"])
        )
        listed += len(rows)
    await session.flush()
    return listed


async def read_summaries(
    session: AsyncSession,
    fetch: Fetch,
    *,
    limit: int = SUMMARIES_PER_RUN,
    concurrency: int = CONCURRENCY,
    rate: float = RATE,
    budget: float = BUDGET,
    now: datetime | None = None,
) -> int:
    """Up to ``limit`` listed filings' cover pages, the latest filed first, none started after
    ``budget`` seconds. How many were read. One that cannot be read is tried ``MAX_ATTEMPTS``
    times in all; SEC answering slowly ends the run."""
    now = now or datetime.now(UTC)
    todo = list(
        (
            await session.scalars(
                select(ThirteenFFiling)
                .where(ThirteenFFiling.read_at.is_(None), ThirteenFFiling.attempts < MAX_ATTEMPTS)
                .order_by(ThirteenFFiling.filed.desc(), ThirteenFFiling.accession)
                .limit(limit)
            )
        ).all()
    )
    gate = asyncio.Semaphore(concurrency)
    loop = asyncio.get_running_loop()
    start = loop.time()
    stopped = asyncio.Event()
    read = 0

    async def one(n: int, filing: ThirteenFFiling) -> None:
        nonlocal read
        async with gate:
            wait = start + n / rate - loop.time() if rate > 0 else 0
            if wait > 0:
                # its turn, or SEC answering slowly ending the run, whichever comes first
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(stopped.wait(), wait)
            if stopped.is_set() or loop.time() - start > budget:
                return
            try:
                summary = await read_summary(fetch, filing.cik, filing.accession)
            except FetchUnavailable as error:
                if not stopped.is_set():
                    log.warning("13f index: SEC is slow (%s); next run", error)
                stopped.set()
                return
            except (thirteenf.FilingError, FetchRefused) as error:
                filing.attempts += 1
                filing.error = str(error)[:500]
                return
            except Exception as error:  # one odd filing must not undo the run, nor block the next
                log.exception("13f index: %s could not be read", filing.accession)
                filing.attempts += 1
                filing.error = f"{type(error).__name__}: {error}"[:500]
                return
        # only attributes are set below: the session itself is not used while others wait
        filing.period = summary.period
        filing.manager = summary.manager or None
        filing.amendment = summary.amendment
        filing.report_type = summary.report_type or None
        filing.entries = summary.entries
        filing.value_usd = summary.value_usd
        filing.read_at = now
        filing.error = None
        read += 1

    await asyncio.gather(*(one(n, f) for n, f in enumerate(todo)))
    await session.flush()
    return read


class IndexKeeper:
    def __init__(self, fetch: Fetch | None) -> None:
        self.fetch = fetch
        """SEC; None offline, and nobody is asked (nor a day taken for a holiday)."""

    def schedule_handler(self) -> Handler:
        """The ``newsroom.refresh_13f_index`` handler: a few days of the index, then a few
        hundred cover pages."""

        async def handler(
            session: AsyncSession, schedule: Schedule, scheduled_for: datetime
        ) -> None:
            if self.fetch is None:
                return
            await read_index(session, self.fetch, today=datetime.now(UTC).date())
            await read_summaries(session, self.fetch)

        return handler


# --- a quarter's totals --------------------------------------------------------------------------


@dataclass(frozen=True)
class Total:
    cik: str
    manager: str
    value_usd: int
    entries: int
    filed: date
    """When its latest filing for the quarter came."""
    accession: str
    """The filing the total starts from: the original, or the restatement."""


def totals(filings: Iterable[ThirteenFFiling]) -> list[Total]:
    """One quarter's filings, as each filer's total, largest first: the latest restatement or
    else the latest original, plus the new-holdings amendments filed after it. Notices, and
    filings not read yet, count for nothing."""
    by_cik: dict[str, list[ThirteenFFiling]] = defaultdict(list)
    for f in filings:
        if f.read_at is not None and f.report_type != NOTICE:
            by_cik[f.cik].append(f)
    out = []
    for cik, mine in by_cik.items():
        order = sorted(mine, key=lambda f: (f.filed, f.accession))
        bases = [f for f in order if f.amendment == RESTATEMENT] or [
            f for f in order if f.form == "13F-HR" and f.amendment is None
        ]
        if not bases:
            continue  # only additions, to a filing not listed: not a quarter
        base = bases[-1]
        after = (base.filed, base.accession)
        added = [f for f in order if f.amendment == NEW_HOLDINGS and (f.filed, f.accession) > after]
        latest = order[-1]
        out.append(
            Total(
                cik=cik,
                manager=latest.manager or base.manager or base.company,
                value_usd=int(base.value_usd or 0) + sum(int(f.value_usd or 0) for f in added),
                entries=int(base.entries or 0) + sum(int(f.entries or 0) for f in added),
                filed=latest.filed,
                accession=base.accession,
            )
        )
    return sorted(out, key=lambda t: (-t.value_usd, t.cik))


async def quarter_totals(session: AsyncSession, period: date) -> list[Total]:
    """Every filer's total for the quarter ending ``period``, largest first."""
    rows = await session.scalars(select(ThirteenFFiling).where(ThirteenFFiling.period == period))
    return totals(rows.all())
