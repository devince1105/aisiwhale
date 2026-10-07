"""One way to ask the back office for a list (AD-04, logs/admin/01_ADMIN_REVAMP_PLAN.md).

``?cursor=&limit=&q=&sort=`` → ``{items, next_cursor, total}``:

- ``limit``: 1–100, 50 when not given.
- ``sort``: one of the endpoint's own keys, ``-`` in front for descending (``-updated_at``). The
  row's id breaks ties in the same direction, so the order is total and stable.
- ``cursor``: opaque, from the previous page's ``next_cursor``; it is the last row's sort value
  and id (keyset paging: a page does not shift when rows are added before it, and costs the same
  deep in the list). It carries its sort, and is refused (400) under another one.
- ``q``: every word somewhere in the endpoint's searched columns, ignoring case.
- ``total``: how many rows the filters (not the cursor) leave.

Errors stay problem+json (problems.py).
"""

from __future__ import annotations

import base64
import binascii
import json
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any

from fastapi import Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import ColumnElement, Select, and_, func, literal, or_, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

DEFAULT_LIMIT = 50
MAX_LIMIT = 100


class Page[T](BaseModel):
    items: list[T]
    next_cursor: str | None = None
    """The next page's ``cursor``; None on the last page."""
    total: int
    """Rows the filters leave, on every page."""


@dataclass(frozen=True)
class ListParams:
    cursor: str | None
    limit: int
    q: str | None

    @property
    def words(self) -> list[str]:
        return (self.q or "").split()


def _list_params(
    cursor: Annotated[str | None, Query(max_length=500)] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
    q: Annotated[str | None, Query(max_length=200)] = None,
) -> ListParams:
    return ListParams(cursor=cursor or None, limit=limit, q=(q or "").strip() or None)


Listing = Annotated[ListParams, Depends(_list_params)]


@dataclass(frozen=True)
class Sort:
    param: str
    """As asked: ``-updated_at``."""
    column: Any
    descending: bool

    @property
    def key(self) -> str:
        return self.param.lstrip("-")


def sort_by(param: str, columns: Mapping[str, Any]) -> Sort:
    """``param`` is one of the endpoint's ``Literal`` values, so FastAPI has checked it."""
    key = param.lstrip("-")
    return Sort(param=param, column=columns[key], descending=param.startswith("-"))


# --- the cursor -------------------------------------------------------------------------------


def _encode(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _decode(raw: str, like: Any) -> Any:
    kind = like.type.python_type
    if kind is datetime:
        return datetime.fromisoformat(raw)
    if kind is Decimal:
        return Decimal(raw)
    return raw


def make_cursor(sort: Sort, value: Any, row_id: uuid.UUID) -> str:
    body = json.dumps(
        {"s": sort.param, "v": _encode(value), "id": str(row_id)}, separators=(",", ":")
    )
    return base64.urlsafe_b64encode(body.encode()).decode().rstrip("=")


def read_cursor(cursor: str, sort: Sort) -> tuple[Any, uuid.UUID]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        body = json.loads(base64.urlsafe_b64decode(padded.encode()))
        if body["s"] != sort.param:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "the cursor is for another sort")
        return _decode(body["v"], sort.column), uuid.UUID(body["id"])
    except HTTPException:
        raise
    except (binascii.Error, ValueError, KeyError, TypeError, UnicodeDecodeError):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid cursor") from None


# --- search -----------------------------------------------------------------------------------


def _like(word: str) -> str:
    escaped = word.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def search(words: Sequence[str], *columns: Any) -> ColumnElement[bool] | None:
    """Every word in one of ``columns`` at least, ignoring case; None for no words."""
    if not words:
        return None
    return and_(
        *(or_(*(column.ilike(_like(word), escape="\\") for column in columns)) for word in words)
    )


def matches(words: Sequence[str], *texts: str | None) -> bool:
    """``search`` for rows already in memory."""
    haystack = " ".join(t for t in texts if t).casefold()
    return all(word.casefold() in haystack for word in words)


# --- a page -----------------------------------------------------------------------------------


async def page_rows(
    session: AsyncSession,
    stmt: Select[Any],
    *,
    sort: Sort,
    id_column: Any,
    listing: ListParams,
    entity: Callable[[Any], Any] = lambda row: row[0],
) -> tuple[list[Any], str | None, int]:
    """A page of ``stmt`` (filtered, not ordered): its rows, the next cursor, the total.
    ``entity(row)`` is the row's object that has the sort column and ``id``."""
    total = await session.scalar(select(func.count()).select_from(stmt.order_by(None).subquery()))
    if listing.cursor:
        value, after = read_cursor(listing.cursor, sort)
        key = tuple_(sort.column, id_column)
        bound = tuple_(literal(value, type_=sort.column.type), literal(after, type_=id_column.type))
        stmt = stmt.where(key < bound if sort.descending else key > bound)
    order = (sort.column.desc(), id_column.desc()) if sort.descending else (sort.column, id_column)
    rows = list((await session.execute(stmt.order_by(*order).limit(listing.limit + 1))).all())
    more = len(rows) > listing.limit
    rows = rows[: listing.limit]
    last = entity(rows[-1]) if rows and more else None
    next_cursor = make_cursor(sort, getattr(last, sort.key), last.id) if last is not None else None
    return rows, next_cursor, int(total or 0)


def page_list[R](
    items: Sequence[R],
    *,
    sort: Sort,
    value: Callable[[R], Any],
    row_id: Callable[[R], uuid.UUID],
    listing: ListParams,
) -> tuple[list[R], str | None, int]:
    """The same page over rows already in memory (a list a domain function returns whole)."""
    ordered = sorted(items, key=lambda r: (value(r), row_id(r)), reverse=sort.descending)
    if listing.cursor:
        bound = read_cursor(listing.cursor, sort)
        after = (lambda k: k < bound) if sort.descending else (lambda k: k > bound)
        ordered = [r for r in ordered if after((value(r), row_id(r)))]
    page = ordered[: listing.limit]
    more = len(ordered) > listing.limit
    next_cursor = make_cursor(sort, value(page[-1]), row_id(page[-1])) if page and more else None
    return page, next_cursor, len(items)
