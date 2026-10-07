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

**Dollars or thousands** (HD-10): values have been in dollars since 2023, but some still file in
thousands — T. Rowe Price's second quarter of 2026 says US$1 billion for about US$1 trillion. The
cover page cannot tell, so a filing whose entries average under ``IN_DOUBT_AVERAGE`` (the 100
largest average over US$4 million) has the first rows of its table read once its run has time to
spare (``check_scales``): most shares worth under a dollar, and its ``scale`` is 1000. Every
total is in dollars.
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
from autora.domains.newsroom import thirteenf, thirteenf_tables
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
IN_DOUBT_AVERAGE = 1_000_000
"""US$ an entry under which a filing may be in thousands, and has its first rows read."""
IN_DOUBT_ENTRIES = 10


def in_doubt(entries: int, value: int) -> bool:
    """Whether a cover page's totals may be in thousands of dollars."""
    return entries >= IN_DOUBT_ENTRIES and 0 < value < IN_DOUBT_AVERAGE * entries


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


async def paced(
    items: list,
    read: Callable[[object], Awaitable[bool]],
    *,
    concurrency: int,
    rate: float,
    budget: float,
    what: str,
) -> int:
    """``read`` each of ``items``: ``concurrency`` at a time, ``rate`` a second at most, none
    started after ``budget`` seconds. How many it says it read. SEC answering slowly
    (``FetchUnavailable``) ends the run at once; every other failure is ``read``'s to keep."""
    gate = asyncio.Semaphore(concurrency)
    loop = asyncio.get_running_loop()
    start = loop.time()
    stopped = asyncio.Event()
    done = 0

    async def one(n: int, item: object) -> None:
        nonlocal done
        turn = n / rate if rate > 0 else 0
        if turn > budget:
            return  # its turn would come after the run's time is up: not waited for either
        async with gate:
            wait = start + turn - loop.time()
            if wait > 0:
                # its turn, or SEC answering slowly ending the run, whichever comes first
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(stopped.wait(), wait)
            if stopped.is_set() or loop.time() - start > budget:
                return
            try:
                ok = await read(item)  # (not ``done += await …``: that reads ``done`` first)
            except FetchUnavailable as error:
                if not stopped.is_set():
                    log.warning("13f index: SEC is slow reading %s (%s); next run", what, error)
                stopped.set()
                return
            done += bool(ok)

    await asyncio.gather(*(one(n, item) for n, item in enumerate(items)))
    return done


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

    async def read(filing: ThirteenFFiling) -> bool:
        try:
            summary = await read_summary(fetch, filing.cik, filing.accession)
        except (thirteenf.FilingError, FetchRefused) as error:
            filing.attempts += 1
            filing.error = str(error)[:500]
            return False
        except FetchUnavailable:
            raise
        except Exception as error:  # one odd filing must not undo the run, nor block the next
            log.exception("13f index: %s could not be read", filing.accession)
            filing.attempts += 1
            filing.error = f"{type(error).__name__}: {error}"[:500]
            return False
        # only attributes are set: the session itself is not used while others wait
        filing.period = summary.period
        filing.manager = summary.manager or None
        filing.amendment = summary.amendment
        filing.report_type = summary.report_type or None
        filing.entries = summary.entries
        filing.value_usd = summary.value_usd
        filing.scale = None if in_doubt(summary.entries, summary.value_usd) else 1
        filing.read_at = now
        filing.error = None
        return True

    read_count = await paced(
        todo, read, concurrency=concurrency, rate=rate, budget=budget, what="cover pages"
    )
    await session.flush()
    return read_count


async def check_scales(
    session: AsyncSession,
    fetch: Fetch,
    chunks: thirteenf_tables.Chunks,
    *,
    limit: int = SUMMARIES_PER_RUN,
    concurrency: int = CONCURRENCY,
    rate: float = RATE / 2,
    budget: float = BUDGET,
) -> int:
    """Up to ``limit`` filings in doubt (``in_doubt``), the largest first: their tables' first
    rows read, and their ``scale`` set. Two requests each (the folder, the table), so half the
    rate. How many were checked. One whose table cannot be read is tried ``MAX_ATTEMPTS`` times."""
    todo = list(
        (
            await session.scalars(
                select(ThirteenFFiling)
                .where(
                    ThirteenFFiling.read_at.is_not(None),
                    ThirteenFFiling.scale.is_(None),
                    ThirteenFFiling.scale_attempts < MAX_ATTEMPTS,
                )
                .order_by(ThirteenFFiling.value_usd.desc(), ThirteenFFiling.accession)
                .limit(limit)
            )
        ).all()
    )

    async def check(filing: ThirteenFFiling) -> bool:
        try:
            url = await thirteenf_tables.table_url(fetch, filing.cik, filing.accession)
            table = await thirteenf_tables.read_table(chunks, url, rows=thirteenf_tables.CHECK_ROWS)
        except (thirteenf.FilingError, FetchRefused) as error:
            filing.scale_attempts += 1
            filing.error = f"scale: {error}"[:500]
            return False
        except FetchUnavailable:
            raise
        except Exception as error:  # as with a cover page: this filing's, not the run's
            log.exception("13f index: %s's table could not be read", filing.accession)
            filing.scale_attempts += 1
            filing.error = f"scale: {type(error).__name__}: {error}"[:500]
            return False
        filing.scale = thirteenf_tables.scale_of(table)
        return True

    checked = await paced(
        todo, check, concurrency=concurrency, rate=rate, budget=budget, what="tables"
    )
    await session.flush()
    return checked


SPARE = 10.0
"""Seconds left in a run below which no table is checked."""


class IndexKeeper:
    def __init__(self, fetch: Fetch | None, chunks: thirteenf_tables.Chunks | None = None) -> None:
        self.fetch = fetch
        """SEC; None offline, and nobody is asked (nor a day taken for a holiday)."""
        self.chunks = chunks
        """SEC's tables, streamed; None offline."""

    def schedule_handler(self) -> Handler:
        """The ``newsroom.refresh_13f_index`` handler: a few days of the index, then a few
        hundred cover pages, then — with what is left of the run — filings in doubt."""

        async def handler(
            session: AsyncSession, schedule: Schedule, scheduled_for: datetime
        ) -> None:
            if self.fetch is None:
                return
            loop = asyncio.get_running_loop()
            start = loop.time()
            await read_index(session, self.fetch, today=datetime.now(UTC).date())
            await read_summaries(session, self.fetch)
            left = BUDGET - (loop.time() - start)
            if self.chunks is not None and left > SPARE:
                await check_scales(session, self.fetch, self.chunks, budget=left)

        return handler


# --- a quarter's totals --------------------------------------------------------------------------


@dataclass(frozen=True)
class Total:
    cik: str
    manager: str
    value_usd: int
    """In dollars: a filing in thousands is multiplied by its ``scale``."""
    entries: int
    filed: date
    """When its latest filing for the quarter came."""
    accession: str
    """The filing the total starts from: the original, or the restatement."""
    accessions: tuple[str, ...] = ()
    """Every filing the total is made of: that one, and the additions after it."""
    in_thousands: bool = False
    """Some of it was filed in thousands of dollars, and is multiplied here."""
    in_doubt: bool = False
    """Some of it may be in thousands and has not been checked yet."""


def composition(filings: Iterable[ThirteenFFiling]) -> list[ThirteenFFiling]:
    """One filer's filings for one quarter, as its total is made of them: the latest restatement
    or else the latest original, then the new-holdings amendments filed after it. Empty when
    there is no quarter (notices, filings not read yet, or additions alone)."""
    order = sorted(
        (f for f in filings if f.read_at is not None and f.report_type != NOTICE),
        key=lambda f: (f.filed, f.accession),
    )
    bases = [f for f in order if f.amendment == RESTATEMENT] or [
        f for f in order if f.form == "13F-HR" and f.amendment is None
    ]
    if not bases:
        return []
    base = bases[-1]
    after = (base.filed, base.accession)
    return [base] + [
        f for f in order if f.amendment == NEW_HOLDINGS and (f.filed, f.accession) > after
    ]


def dollars(filing: ThirteenFFiling) -> int:
    return int(filing.value_usd or 0) * (filing.scale or 1)


def totals(filings: Iterable[ThirteenFFiling]) -> list[Total]:
    """One quarter's filings, as each filer's total, largest first (``composition``). Notices,
    and filings not read yet, count for nothing."""
    by_cik: dict[str, list[ThirteenFFiling]] = defaultdict(list)
    for f in filings:
        by_cik[f.cik].append(f)
    out = []
    for cik, mine in by_cik.items():
        parts = composition(mine)
        if not parts:
            continue
        base = parts[0]
        latest = max(
            (f for f in mine if f.read_at is not None), key=lambda f: (f.filed, f.accession)
        )
        out.append(
            Total(
                cik=cik,
                manager=latest.manager or base.manager or base.company,
                value_usd=sum(dollars(f) for f in parts),
                entries=sum(int(f.entries or 0) for f in parts),
                filed=latest.filed,
                accession=base.accession,
                accessions=tuple(f.accession for f in parts),
                in_thousands=any(f.scale == 1000 for f in parts),
                in_doubt=any(f.scale is None for f in parts),
            )
        )
    return sorted(out, key=lambda t: (-t.value_usd, t.cik))


async def quarter_totals(session: AsyncSession, period: date) -> list[Total]:
    """Every filer's total for the quarter ending ``period``, largest first."""
    rows = await session.scalars(select(ThirteenFFiling).where(ThirteenFFiling.period == period))
    return totals(rows.all())


async def quarter_of(session: AsyncSession, cik: str, period: date) -> list[ThirteenFFiling]:
    """One filer's filings making up its quarter (``composition``)."""
    rows = await session.scalars(
        select(ThirteenFFiling).where(
            ThirteenFFiling.cik == cik.lstrip("0"), ThirteenFFiling.period == period
        )
    )
    return composition(rows.all())


DEADLINE = timedelta(days=45)
"""13Fs are due 45 days after the quarter ends."""


def quarter_end(day: date) -> date:
    """The last day of the quarter ``day`` is in."""
    month = (day.month - 1) // 3 * 3 + 3
    following = date(day.year + month // 12, month % 12 + 1, 1)
    return following - timedelta(days=1)


def previous_period(period: date) -> date:
    """The quarter before's last day: 2026-06-30 → 2026-03-31."""
    return quarter_end(period.replace(day=1) - timedelta(days=80))


def ranked_period(today: date) -> date:
    """The latest quarter whose 13Fs were all due by yesterday: the one a ranking shows, so
    that it is not half the filers'."""
    period = previous_period(quarter_end(today))
    while period + DEADLINE >= today:
        period = previous_period(period)
    return period
