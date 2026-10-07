"""A 13F's information table, read as it downloads (HD-10, D-217).

``thirteenf.parse_filing`` reads a whole submission into memory and parses it as one tree — right
for the few filers the site follows, wrong for BlackRock's 50,000 rows (a 23 MB table, several
hundred MB as a tree, on a worker with 512 MB). Here the table is fed to an incremental parser a
chunk at a time, each row added to its position (CUSIP, put or call, shares or principal) and
dropped: what is kept is the positions, not the document.

Two uses: the whole table, for an institution's page (``institution_details``); and its first
rows only, to tell whether a filing's values are dollars or — against the rule since 2023 —
thousands of dollars (``scale_of``; T. Rowe Price's second quarter of 2026 was the latter).

The table is found from the filing's folder (``index.json``): its XML file other than the cover
page, the largest if there are several. DTDs and entities are refused, as in ``thirteenf``.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import aclosing
from dataclasses import dataclass
from urllib.parse import urlsplit
from xml.etree import ElementTree as ET

import httpx

from autora.domains.newsroom import thirteenf
from autora.infra.http import FetchRefused, FetchUnavailable

Fetch = Callable[[str], Awaitable[bytes]]
Chunks = Callable[[str], AsyncIterator[bytes]]
"""A document as it downloads, a chunk at a time; stopping early closes the download."""

SEC_HOST = "www.sec.gov"
MAX_TABLE_BYTES = 300_000_000
"""Larger than any table yet (BlackRock's: 23 MB), small enough to stop a runaway download."""
CHECK_ROWS = 200
"""Rows enough to tell dollars from thousands."""
_UNSAFE = (b"<!DOCTYPE", b"<!ENTITY")


def sec_chunks(
    user_agent: str, *, timeout: float = 30.0, max_bytes: int = MAX_TABLE_BYTES
) -> Chunks:
    """SEC's archive, streamed. Only ``www.sec.gov``: the addresses are made here, never taken
    from a page. 429 and 5xx, and a connection that fails, are ``FetchUnavailable`` (try later);
    other 4xx are ``FetchRefused``."""

    async def chunks(url: str) -> AsyncIterator[bytes]:
        if urlsplit(url).hostname != SEC_HOST:
            raise FetchRefused(f"only {SEC_HOST} is read here: {url[:200]}")
        try:
            async with httpx.AsyncClient(
                timeout=timeout, headers={"User-Agent": user_agent}, follow_redirects=False
            ) as client:
                async with client.stream("GET", url) as response:
                    status = response.status_code
                    if status == 429 or status >= 500:
                        raise FetchUnavailable(f"{url} answered {status}")
                    if status >= 300:
                        raise FetchRefused(f"{url} answered {status}")
                    received = 0
                    async for chunk in response.aiter_bytes():
                        received += len(chunk)
                        if received > max_bytes:
                            raise FetchRefused(f"{url} is larger than {max_bytes} bytes")
                        yield chunk
        except httpx.HTTPError as exc:
            raise FetchUnavailable(f"{url}: {type(exc).__name__}") from None

    return chunks


async def table_url(fetch: Fetch, cik: str, accession: str) -> str:
    """The filing's information table: its folder's XML file that is not the cover page (the
    largest, when there are several)."""
    folder = f"{thirteenf.ARCHIVES}/{cik}/{accession.replace('-', '')}"
    try:
        items = json.loads(await fetch(f"{folder}/index.json"))["directory"]["item"]
    except (KeyError, TypeError, ValueError) as exc:
        raise thirteenf.FilingError(f"the filing's folder could not be read: {exc}") from exc
    tables = [
        item
        for item in items
        if str(item.get("name", "")).lower().endswith(".xml")
        and str(item.get("name")) != "primary_doc.xml"
    ]
    if not tables:
        raise thirteenf.FilingError("no information table in the filing")
    largest = max(tables, key=lambda item: int(str(item.get("size") or 0) or 0))
    return f"{folder}/{largest['name']}"


@dataclass
class Table:
    holdings: thirteenf.Holdings
    """Values as filed: dollars, or thousands (``scale_of``)."""
    rows: int
    complete: bool
    """False when only the first rows were read."""


def _row(element: ET.Element) -> tuple[thirteenf.Position, int, int]:
    text = thirteenf._child_text
    position = thirteenf.Position(
        name=text(element, "nameOfIssuer"),
        title_of_class=text(element, "titleOfClass"),
        cusip=text(element, "cusip").upper(),
        put_call=text(element, "putCall").upper(),
        kind=text(element, "sshPrnamtType").upper() or "SH",
    )
    return (
        position,
        thirteenf._int(text(element, "sshPrnamt")),
        thirteenf._int(text(element, "value")),
    )


async def read_table(chunks: Chunks, url: str, *, rows: int | None = None) -> Table:
    """The table at ``url``, row by row as it downloads: all of it, or its first ``rows``."""
    holdings = thirteenf.Holdings(manager="", report_type="")
    parser = ET.XMLPullParser(events=("start", "end"))
    root: ET.Element | None = None
    tail = b""
    count = 0
    async with aclosing(chunks(url)) as stream:
        async for chunk in stream:
            seen = tail + chunk
            if any(mark in seen for mark in _UNSAFE):
                raise thirteenf.FilingError("the table declares a DTD or entities; refused")
            tail = seen[-16:]
            parser.feed(chunk)
            try:
                events = list(parser.read_events())
            except ET.ParseError as exc:
                raise thirteenf.FilingError(f"the table's XML could not be read: {exc}") from exc
            for event, element in events:
                if root is None:
                    root = element
                    if thirteenf._local(element.tag) != "informationTable":
                        raise thirteenf.FilingError("not an information table")
                    continue
                if event != "end" or thirteenf._local(element.tag) != "infoTable":
                    continue
                position, amount, value = _row(element)
                held = holdings.positions.setdefault(position.key, position)
                held.amount += amount
                held.value += value
                count += 1
                root.clear()  # the row is counted: nothing of it is kept but its position
                if rows is not None and count >= rows:
                    return Table(holdings, count, complete=False)
    try:
        parser.close()
    except ET.ParseError as exc:
        raise thirteenf.FilingError(f"the table's XML could not be read: {exc}") from exc
    if root is None:
        raise thirteenf.FilingError("an empty information table")
    return Table(holdings, count, complete=True)


def scale_of(table: Table) -> int:
    """1000 when most shares come out worth under a dollar each — the values were written in
    thousands (``thirteenf._looks_like_thousands``); else 1."""
    return 1000 if thirteenf._looks_like_thousands(table.holdings) else 1


APART = 1000**0.5
"""Between "the same" and "a thousand times as much", on a log scale: a total estimated from
a table's first rows is off by a few times at most, never by thirty."""


def total_scale(table: Table, rows_scale: int, entries: int, total: int) -> int:
    """What a cover page's total is multiplied by to be dollars. Its rows in dollars, and so is
    the total. Its rows in thousands: the table's dollars — all of it, or its first rows' as
    many times over as it has entries — are a thousand times the total when it was written in
    thousands too (T. Rowe Price, 2026Q2), about the same when it was written in dollars after
    all (Coston, McIsaac & Partners wrote its rows in thousands and its total in dollars)."""
    if rows_scale == 1 or total <= 0:
        return 1
    rows_value = sum(p.value for p in table.holdings.positions.values())
    if not table.complete and table.rows:
        rows_value = rows_value * max(entries, table.rows) / table.rows
    return 1000 if rows_value * rows_scale / total >= APART else 1


def scaled(table: Table, scale: int) -> thirteenf.Holdings:
    """The table's holdings in dollars."""
    holdings = table.holdings
    if scale != 1:
        for held in holdings.positions.values():
            held.value *= scale
        holdings.in_thousands = True
    return holdings
