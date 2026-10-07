"""Who may open the back office, and as what (AD-09, D-234 ①). An owner's (``access:manage``).

- GET    /api/admin/access               → the owners from ADMIN_EMAILS, the people let in with
                                           their roles, and what each role may do
- POST   /api/admin/access               {email, role} → let a signed-up reader in
- PUT    /api/admin/access/{reader_id}   {role} → change their role
- DELETE /api/admin/access/{reader_id}   → take them out

ADMIN_EMAILS are owners from the environment and are not changed here. Nobody changes or removes
their own role here (an owner cannot lock themselves out by a slip). Every change is in the
audit trail (AD-06), who and what.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from autora.accounts import AccountError, by_email
from autora.accounts.models import Reader
from autora.db.models import AdminRole, AdminRoleName
from autora.infra.settings import Settings
from autora_api import permissions
from autora_api.deps import Operator, Session, settings_dep

router = APIRouter(prefix="/api/admin/access", tags=["admin-access"])
SettingsDep = Annotated[Settings, Depends(settings_dep)]

ADMIN = "admin:"


class Member(BaseModel):
    reader_id: uuid.UUID
    email: str
    role: AdminRoleName
    granted_by: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class Access(BaseModel):
    owners: list[str]
    """ADMIN_EMAILS: owners, from the environment."""
    members: list[Member]
    roles: dict[str, list[str]]
    """What each role may do."""


class LetIn(BaseModel):
    email: str = Field(max_length=254)
    role: AdminRoleName


class ChangeRole(BaseModel):
    role: AdminRoleName


def _member(row: AdminRole, email: str) -> Member:
    return Member(
        reader_id=row.reader_id,
        email=email,
        role=AdminRoleName(row.role),
        granted_by=row.granted_by,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _not_yourself(actor, reader_id: uuid.UUID) -> None:
    if actor.id == f"{ADMIN}{reader_id}":
        raise HTTPException(status.HTTP_409_CONFLICT, "you cannot change your own role")


@router.get("")
async def access(session: Session, _: Operator, settings: SettingsDep) -> Access:
    rows = (
        await session.execute(
            select(AdminRole, Reader.email)
            .join(Reader, Reader.id == AdminRole.reader_id)
            .order_by(AdminRole.created_at, AdminRole.reader_id)
        )
    ).all()
    return Access(
        owners=sorted(settings.admin_emails),
        members=[_member(row, email) for row, email in rows],
        roles={role.value: sorted(permissions.permissions_of(role)) for role in AdminRoleName},
    )


@router.post("", status_code=status.HTTP_201_CREATED)
async def let_in(body: LetIn, session: Session, actor: Operator, settings: SettingsDep) -> Member:
    """The reader must have signed up; they open the back office once their address is proven."""
    try:
        reader = await by_email(session, body.email)
    except AccountError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    if reader is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no reader has this address")
    if reader.email in set(settings.admin_emails):
        raise HTTPException(status.HTTP_409_CONFLICT, "already an owner (ADMIN_EMAILS)")
    if await session.get(AdminRole, reader.id) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "already let in; change their role instead")
    row = AdminRole(reader_id=reader.id, role=body.role.value, granted_by=actor.model_dump())
    session.add(row)
    await session.flush()
    await session.refresh(row)
    await session.commit()
    return _member(row, reader.email)


@router.put("/{reader_id}")
async def change_role(
    reader_id: uuid.UUID, body: ChangeRole, session: Session, actor: Operator
) -> Member:
    _not_yourself(actor, reader_id)
    row = await session.get(AdminRole, reader_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not let in")
    row.role = body.role.value
    row.granted_by = actor.model_dump()
    await session.flush()
    await session.refresh(row)
    reader = await session.get(Reader, reader_id)
    await session.commit()
    return _member(row, reader.email if reader else "")


@router.delete("/{reader_id}", status_code=status.HTTP_204_NO_CONTENT)
async def take_out(reader_id: uuid.UUID, session: Session, actor: Operator) -> None:
    _not_yourself(actor, reader_id)
    row = await session.get(AdminRole, reader_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not let in")
    await session.delete(row)
    await session.commit()
