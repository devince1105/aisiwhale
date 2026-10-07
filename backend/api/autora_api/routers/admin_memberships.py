"""VIP given by an admin, for internal testing (D-228, P2).

- POST /api/admin/memberships/comps                    {email, until, reason, company?} -> 201
- GET  /api/admin/memberships/comps[?company&running]  -> the comps, newest first, a page at a time
                                                         (?cursor=&limit=&q=&sort=, AD-04)
- GET  /api/admin/memberships/comps/{grant_id}         -> one comp
- POST /api/admin/memberships/comps/{grant_id}/revoke  {reason} -> the comp, ended now

The back office's own (``Operator``: an admin signed in, or the operator token). A comp makes
no order, no payment, no ledger row and no revenue: it is ``memberships.grant_comp``, never
``purchase``. Its actor is the admin, by reader id (``admin:<id>``), never by address. Ending a
comp revokes it — the row keeps who, when and why — and access falls back to whatever else is
still running.

This is the one place addresses meet memberships: the accounts layer finds the reader by email,
the company layer knows them only as ``reader:<id>``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from autora.accounts import AccountError, Reader, by_email, customer_ref
from autora.company import memberships
from autora.company.memberships import REASON_MAX, MembershipError
from autora.db.models import Company, MembershipGrant
from autora_api import export
from autora_api.deps import Operator, Session
from autora_api.pagination import Listing, Page, matches, page_list, sort_by

router = APIRouter(prefix="/api/admin/memberships", tags=["admin-memberships"])

CompanySlug = Annotated[str | None, Query(max_length=100)]


class GrantComp(BaseModel):
    email: str = Field(max_length=254)
    """The reader to give VIP to. They must have signed up already."""
    until: datetime
    """When it ends. A comp gives exactly this, in the future."""
    reason: str = Field(min_length=1, max_length=REASON_MAX)
    company: str | None = Field(default=None, max_length=100)


class Revoke(BaseModel):
    reason: str = Field(min_length=1, max_length=REASON_MAX)


class Comp(BaseModel):
    id: uuid.UUID
    reader_id: uuid.UUID | None
    email: str | None
    """The reader's address, for the admin; None if the reader is gone."""
    source: str
    started_at: datetime
    expires_at: datetime
    reason: str | None
    actor: dict[str, Any]
    revoked_at: datetime | None
    revoked_by: dict[str, Any] | None
    revoke_reason: str | None
    running: bool
    """Giving access right now: not revoked and not run out."""


class CompPage(Page[Comp]):
    pass


CompSort = Literal["-created_at", "created_at", "-expires_at", "expires_at"]


async def _company(session, slug: str | None) -> Company:
    query = select(Company) if slug is None else select(Company).where(Company.slug == slug)
    company = await session.scalar(query.order_by(Company.created_at).limit(1))
    if company is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such company")
    return company


def _reader_id(ref: str) -> uuid.UUID | None:
    prefix = customer_ref(uuid.UUID(int=0)).split(":")[0] + ":"
    if not ref.startswith(prefix):
        return None
    try:
        return uuid.UUID(ref[len(prefix) :])
    except ValueError:
        return None


async def _view(session, grant: MembershipGrant, ref: str, now: datetime) -> Comp:
    reader_id = _reader_id(ref)
    reader = await session.get(Reader, reader_id) if reader_id is not None else None
    return Comp(
        id=grant.id,
        reader_id=reader_id,
        email=reader.email if reader is not None else None,
        source=grant.source,
        started_at=grant.started_at,
        expires_at=grant.expires_at,
        reason=grant.reason,
        actor=grant.actor,
        revoked_at=grant.revoked_at,
        revoked_by=grant.revoked_by,
        revoke_reason=grant.revoke_reason,
        running=grant.revoked_at is None and grant.expires_at > now,
    )


@router.post("/comps", status_code=status.HTTP_201_CREATED)
async def grant_comp(body: GrantComp, session: Session, actor: Operator) -> Comp:
    """Give a reader VIP until ``until``. No order, no payment, no revenue."""
    company = await _company(session, body.company)
    product = await memberships.product_by_key(session, company.id)
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "this company has no membership")
    try:
        reader = await by_email(session, body.email)
    except AccountError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    if reader is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no reader has this address")
    until = body.until if body.until.tzinfo else body.until.replace(tzinfo=UTC)
    now = datetime.now(UTC)
    try:
        grant = await memberships.grant_comp(
            session,
            product,
            customer_ref=customer_ref(reader.id),
            until=until,
            reason=body.reason,
            actor=actor,
            now=now,
        )
    except MembershipError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    view = await _view(session, grant, customer_ref(reader.id), now)
    await session.commit()
    return view


@router.get("/comps")
async def list_comps(
    session: Session,
    _: Operator,
    listing: Listing,
    company: CompanySlug = None,
    running: bool = False,
    sort: CompSort = "-created_at",
) -> CompPage:
    """``q`` searches the reader's address and the reasons. Comps are few (internal testing),
    so the page is cut from the whole list here rather than in SQL."""
    found = await _company(session, company)
    now = datetime.now(UTC)
    rows = await memberships.comp_grants(session, found.id, running_at=now if running else None)
    views = [(grant, await _view(session, grant, ref, now)) for grant, ref in rows]
    if listing.words:
        views = [
            (grant, view)
            for grant, view in views
            if matches(listing.words, view.email, view.reason, view.revoke_reason)
        ]
    columns = {"created_at": MembershipGrant.created_at, "expires_at": MembershipGrant.expires_at}
    order = sort_by(sort, columns)
    page, next_cursor, total = page_list(
        views,
        sort=order,
        value=lambda pair: getattr(pair[0], order.key),
        row_id=lambda pair: pair[0].id,
        listing=listing,
    )
    return CompPage(items=[view for _, view in page], next_cursor=next_cursor, total=total)


COMP_COLUMNS: list[export.Column] = [
    ("讀者", lambda c: c.email or "（讀者已不存在）"),
    ("有效中", lambda c: c.running),
    ("開始", lambda c: c.started_at),
    ("到期", lambda c: c.expires_at),
    ("理由", lambda c: c.reason),
    ("授予者", lambda c: c.actor.get("id")),
    ("撤銷時間", lambda c: c.revoked_at),
    ("撤銷理由", lambda c: c.revoke_reason),
    ("來源", lambda c: c.source),
    ("id", lambda c: c.id),
]


# before /comps/{grant_id}, which would take "export" for an id
@router.get("/comps/export", **export.ROUTE)
async def export_comps(
    request: Request,
    session: Session,
    actor: Operator,
    listing: Listing,
    company: CompanySlug = None,
    running: bool = False,
    sort: CompSort = "-created_at",
) -> StreamingResponse:
    """The comps list as CSV (AD-13): readers' addresses leave the back office, so it is in the
    audit trail with who took it."""
    found = await _company(session, company)
    return await export.csv_export(
        session,
        request,
        actor,
        name="vip-comps",
        columns=COMP_COLUMNS,
        fetch=lambda page: list_comps(session, actor, page, company, running, sort),
        listing=listing,
        company_id=found.id,
    )


@router.get("/comps/{grant_id}")
async def get_comp(
    grant_id: uuid.UUID, session: Session, _: Operator, company: CompanySlug = None
) -> Comp:
    found = await _company(session, company)
    row = await memberships.grant_by_id(session, grant_id, company_id=found.id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such comp")
    return await _view(session, *row, datetime.now(UTC))


@router.post("/comps/{grant_id}/revoke")
async def revoke_comp(
    grant_id: uuid.UUID,
    body: Revoke,
    session: Session,
    actor: Operator,
    company: CompanySlug = None,
) -> Comp:
    """End a comp now. The row is kept, with who ended it, when and why."""
    found = await _company(session, company)
    now = datetime.now(UTC)
    try:
        grant = await memberships.revoke_grant(
            session, grant_id, reason=body.reason, actor=actor, company_id=found.id, now=now
        )
    except MembershipError as exc:
        message = str(exc)
        if "no such grant" in message:
            code = status.HTTP_404_NOT_FOUND
        elif "already revoked" in message or "only a comp" in message:
            code = status.HTTP_409_CONFLICT
        else:
            code = status.HTTP_422_UNPROCESSABLE_CONTENT
        raise HTTPException(code, str(exc)) from exc
    row = await memberships.grant_by_id(session, grant.id)
    assert row is not None
    view = await _view(session, *row, now)
    await session.commit()
    return view
