"""What a signed-in admin asked the back office for (AD-10).

- GET /api/admin/me/prefs → {approvals_digest}
- PUT /api/admin/me/prefs {approvals_digest} → the same, changed

One's own, whatever the role (``self:prefs``). The operator token is nobody's: 409.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from autora.db.models import AdminPref
from autora_api.deps import Operator, Session

router = APIRouter(prefix="/api/admin/me", tags=["admin-me"])
ADMIN = "admin:"


class Prefs(BaseModel):
    approvals_digest: bool = True
    """The daily email of approvals waiting (AD-10); only to a role that decides them."""


def _reader(actor) -> uuid.UUID:
    if not actor.id.startswith(ADMIN):
        raise HTTPException(status.HTTP_409_CONFLICT, "the operator token has no preferences")
    return uuid.UUID(actor.id[len(ADMIN) :])


@router.get("/prefs")
async def get_prefs(session: Session, actor: Operator) -> Prefs:
    row = await session.get(AdminPref, _reader(actor))
    return Prefs(approvals_digest=row.approvals_digest) if row else Prefs()


@router.put("/prefs")
async def put_prefs(body: Prefs, session: Session, actor: Operator) -> Prefs:
    reader_id = _reader(actor)
    row = await session.get(AdminPref, reader_id)
    if row is None:
        session.add(AdminPref(reader_id=reader_id, approvals_digest=body.approvals_digest))
    else:
        row.approvals_digest = body.approvals_digest
    await session.commit()
    return body
