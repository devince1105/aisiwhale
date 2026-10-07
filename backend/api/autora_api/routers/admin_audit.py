"""The back office's record of who did what (AD-06, D-234).

- GET /api/admin/audit[?company_id&actor&target_type&target_id&action&failed&since&until]
  → the changes made through the back office, newest first, a page at a time
  (?cursor=&limit=&q=&sort=, AD-04)

Written by ``audit.AuditMiddleware``; read here only. An admin is named by address for the one
reading (``actor_label``), and stored by reader id (D-024).
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select

from autora.accounts.models import Reader
from autora.db.models import AdminAction
from autora_api import export
from autora_api.deps import Operator, Session
from autora_api.pagination import Listing, ListParams, Page, page_rows, search, sort_by

router = APIRouter(prefix="/api/admin/audit", tags=["admin-audit"])

ADMIN = "admin:"


class AdminActionOut(BaseModel):
    id: uuid.UUID
    created_at: datetime
    actor: dict[str, Any]
    actor_label: str
    """Who, for a person to read: an admin's address, ``操作者權杖`` for the token."""
    method: str
    route: str
    action: str
    target_type: str | None
    target_id: str | None
    company_id: uuid.UUID | None
    status: int
    input: dict[str, Any]
    ip: str | None


class AdminActionPage(Page[AdminActionOut]):
    pass


AuditSort = Literal["-created_at", "created_at"]


async def _labels(session, actors: list[dict[str, Any]]) -> dict[str, str]:
    ids = {
        uuid.UUID(a["id"][len(ADMIN) :])
        for a in actors
        if str(a.get("id", "")).startswith(ADMIN) and _is_uuid(a["id"][len(ADMIN) :])
    }
    found = (
        (await session.execute(select(Reader.id, Reader.email).where(Reader.id.in_(ids)))).all()
        if ids
        else []
    )
    return {f"{ADMIN}{reader_id}": email for reader_id, email in found}


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
    except ValueError:
        return False
    return True


def _label(actor: dict[str, Any], emails: dict[str, str]) -> str:
    ident = str(actor.get("id", ""))
    if ident == "operator":
        return "操作者權杖"
    return emails.get(ident, ident or "—")


@router.get("")
async def list_admin_actions(
    session: Session,
    _: Operator,
    listing: Listing,
    company_id: uuid.UUID | None = None,
    actor: Annotated[str | None, Query(max_length=200)] = None,
    target_type: Annotated[str | None, Query(max_length=50)] = None,
    target_id: Annotated[str | None, Query(max_length=100)] = None,
    action: Annotated[str | None, Query(max_length=100)] = None,
    failed: bool | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    sort: AuditSort = "-created_at",
) -> AdminActionPage:
    """``q`` searches the route, the action, the target's id and who (by stored id). ``failed``:
    only refused (4xx/5xx) or only done (2xx/3xx)."""
    stmt = select(AdminAction)
    if company_id is not None:
        stmt = stmt.where(AdminAction.company_id == company_id)
    if actor:
        stmt = stmt.where(AdminAction.actor["id"].astext == actor)
    if target_type:
        stmt = stmt.where(AdminAction.target_type == target_type)
    if target_id:
        stmt = stmt.where(AdminAction.target_id == target_id)
    if action:
        stmt = stmt.where(AdminAction.action == action)
    if failed is not None:
        stmt = stmt.where(AdminAction.status >= 400 if failed else AdminAction.status < 400)
    if since is not None:
        stmt = stmt.where(AdminAction.created_at >= since)
    if until is not None:
        stmt = stmt.where(AdminAction.created_at < until)
    words = search(
        listing.words,
        AdminAction.route,
        AdminAction.action,
        AdminAction.target_id,
        AdminAction.actor["id"].astext,
    )
    if words is not None:
        stmt = stmt.where(words)
    rows, next_cursor, total = await page_rows(
        session,
        stmt,
        sort=sort_by(sort, {"created_at": AdminAction.created_at}),
        id_column=AdminAction.id,
        listing=listing,
    )
    actions = [row for (row,) in rows]
    emails = await _labels(session, [a.actor for a in actions])
    return AdminActionPage(
        items=[
            AdminActionOut(
                **{k: getattr(a, k) for k in AdminActionOut.model_fields if k != "actor_label"},
                actor_label=_label(a.actor, emails),
            )
            for a in actions
        ],
        next_cursor=next_cursor,
        total=total,
    )


AUDIT_COLUMNS: list[export.Column] = [
    ("時間", lambda a: a.created_at),
    ("誰", lambda a: a.actor_label),
    ("方法", lambda a: a.method),
    ("路由", lambda a: a.route),
    ("動作", lambda a: a.action),
    ("對象種類", lambda a: a.target_type),
    ("對象 id", lambda a: a.target_id),
    ("公司 id", lambda a: a.company_id),
    ("結果", lambda a: a.status),
    ("送出的內容", lambda a: a.input),
    ("來源 IP", lambda a: a.ip),
    ("id", lambda a: a.id),
]


@router.get("/export", **export.ROUTE)
async def export_admin_actions(
    request: Request,
    session: Session,
    operator: Operator,
    listing: Listing,
    company_id: uuid.UUID | None = None,
    actor: Annotated[str | None, Query(max_length=200)] = None,
    target_type: Annotated[str | None, Query(max_length=50)] = None,
    target_id: Annotated[str | None, Query(max_length=100)] = None,
    action: Annotated[str | None, Query(max_length=100)] = None,
    failed: bool | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    sort: AuditSort = "-created_at",
) -> StreamingResponse:
    """The audit trail as CSV (AD-13): the same filters, every page; ``audit:view`` as the list."""

    def fetch(page: ListParams) -> Awaitable[AdminActionPage]:
        return list_admin_actions(
            session,
            operator,
            page,
            company_id,
            actor,
            target_type,
            target_id,
            action,
            failed,
            since,
            until,
            sort,
        )

    return await export.csv_export(
        session,
        request,
        operator,
        name="audit",
        columns=AUDIT_COLUMNS,
        fetch=fetch,
        listing=listing,
        company_id=company_id,
    )
