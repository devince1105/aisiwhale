"""A back-office list as a CSV file (AD-13, D-234): what the table shows, every page of it.

Each list has an ``…/export`` beside it taking the same filters, search and sort; it asks the
list itself page by page (so the rows are exactly the table's, in its order), at most
``EXPORT_LIMIT`` of them, and sends them as CSV:

- UTF-8 with a byte-order mark, so Excel reads the Chinese;
- the table's own words for the headers, times in Taipei's ``YYYY-MM-DD HH:MM``, 是／否;
- a cell that starts like a formula (``=``, ``+``, ``-``, ``@``) gets a ``'`` in front: a
  headline from a feed is not a formula for the spreadsheet to run;
- ``X-Export-Rows`` and ``X-Export-Total`` say how many were sent of how many the filters leave.

An export is a read, which the audit middleware does not record (audit.py); it is recorded
here instead — who took which list, with which filters, how many rows: a file of readers'
emails leaving the back office is the kind of thing the audit trail is for.
"""

from __future__ import annotations

import csv
import io
import json
import uuid
from collections.abc import Awaitable, Callable, Iterator, Sequence
from datetime import datetime
from decimal import Decimal
from typing import Any
from urllib.parse import parse_qsl, quote
from zoneinfo import ZoneInfo

from fastapi import Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from autora.db.models import AdminAction
from autora.runtime.actor import Actor
from autora_api import audit
from autora_api.pagination import MAX_LIMIT, ListParams, Page

EXPORT_LIMIT = 10_000
TAIPEI = ZoneInfo("Asia/Taipei")
FORMULA = ("=", "+", "-", "@", "\t", "\r")

type Column = tuple[str, Callable[[Any], Any]]
"""A header, and how to read the cell from a row."""


async def every_row(
    fetch: Callable[[ListParams], Awaitable[Page[Any]]], listing: ListParams
) -> tuple[list[Any], int]:
    """The list's rows, page after page from the first, up to ``EXPORT_LIMIT``; and its total."""
    rows: list[Any] = []
    cursor: str | None = None
    while True:
        page = await fetch(ListParams(cursor=cursor, limit=MAX_LIMIT, q=listing.q))
        rows.extend(page.items)
        cursor = page.next_cursor
        if cursor is None or len(rows) >= EXPORT_LIMIT:
            return rows[:EXPORT_LIMIT], page.total


def cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, datetime):
        return value.astimezone(TAIPEI).strftime("%Y-%m-%d %H:%M")
    if isinstance(value, dict | list):
        text = json.dumps(value, ensure_ascii=False, default=str)
    elif isinstance(value, Decimal | uuid.UUID | int | float):
        return str(value)
    else:
        text = str(value)
    return f"'{text}" if text.startswith(FORMULA) else text


def _lines(columns: Sequence[Column], rows: Sequence[Any]) -> Iterator[str]:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")

    def line(values: Sequence[str]) -> str:
        buffer.seek(0)
        buffer.truncate()
        writer.writerow(values)
        return buffer.getvalue()

    yield "﻿" + line([header for header, _ in columns])
    for row in rows:
        yield line([cell(read(row)) for _, read in columns])


async def _record(
    session: AsyncSession,
    request: Request,
    actor: Actor,
    *,
    company_id: uuid.UUID | None,
    rows: int,
    total: int,
) -> None:
    route = request.scope.get("route")
    query = dict(parse_qsl(request.url.query))
    session.add(
        AdminAction(
            actor=actor.model_dump(mode="json"),
            method=request.method,
            route=getattr(route, "path", request.url.path),
            action=getattr(route, "name", None) or request.url.path,
            target_type="company" if company_id else None,
            target_id=str(company_id) if company_id else None,
            company_id=company_id,
            status=200,
            input={"query": query, "rows": rows, "total": total},
            ip=audit.client_ip(request.scope),
        )
    )
    await session.commit()


async def csv_export(
    session: AsyncSession,
    request: Request,
    actor: Actor,
    *,
    name: str,
    columns: Sequence[Column],
    fetch: Callable[[ListParams], Awaitable[Page[Any]]],
    listing: ListParams,
    company_id: uuid.UUID | None = None,
) -> StreamingResponse:
    """Every row of a list as ``{name}-{date}.csv``, recorded in the audit trail."""
    rows, total = await every_row(fetch, listing)
    await _record(session, request, actor, company_id=company_id, rows=len(rows), total=total)
    filename = f"{name}-{datetime.now(TAIPEI):%Y%m%d-%H%M}.csv"
    return StreamingResponse(
        _lines(columns, rows),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
            "X-Export-Rows": str(len(rows)),
            "X-Export-Total": str(total),
        },
    )


ROUTE: dict[str, Any] = {
    "response_class": StreamingResponse,
    "responses": {200: {"content": {"text/csv": {}}, "description": "The list as CSV."}},
}
"""What an ``…/export`` route passes to its decorator."""
