"""What the back office tunes while everything runs (AD-11, D-234). An owner's (system:settings).

- GET    /api/admin/settings          → each setting: its value, the environment's, whether the
                                        back office set it, by whom, and its last changes
- PUT    /api/admin/settings/{key}    {value} → set it (checked: type and bounds; shifts parse)
- DELETE /api/admin/settings/{key}    → back to the environment's

A save takes effect without a deploy: this API at once (it holds them in memory), the worker at
its next pass on a shift or when a call is about to begin (runtime/live_settings.py). Every
change is kept with what it was before and after (system_setting_changes) — and is in the audit
trail (AD-06).
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select

from autora.db.models import SystemSetting, SystemSettingChange
from autora.infra.settings import Settings
from autora.runtime.live_settings import DEFINITIONS, SettingError, default, normalize
from autora_api.deps import Operator, Session, settings_dep
from autora_api.live import LIVE
from autora_api.routers.admin_audit import _label, _labels

router = APIRouter(prefix="/api/admin/settings", tags=["admin-settings"])
SettingsDep = Annotated[Settings, Depends(settings_dep)]
HISTORY = 10


class Change(BaseModel):
    before: Any | None
    after: Any | None
    actor: dict[str, Any]
    actor_label: str
    """Who, for a person: an admin's address, 操作者權杖 for the token."""
    at: datetime


class SettingView(BaseModel):
    key: str
    kind: str
    label: str
    help: str
    minimum: float | None
    maximum: float | None
    value: Any
    default: Any
    """The environment's."""
    overridden: bool
    updated_by: dict[str, Any] | None
    updated_at: datetime | None
    changes: list[Change]


class NewValue(BaseModel):
    value: Any


async def _views(session, settings: Settings) -> list[SettingView]:
    rows = {row.key: row for row in (await session.scalars(select(SystemSetting))).all()}
    changes: dict[str, list[Change]] = {}
    for change in (
        await session.scalars(
            select(SystemSettingChange).order_by(
                SystemSettingChange.at.desc(), SystemSettingChange.id.desc()
            )
        )
    ).all():
        listed = changes.setdefault(change.key, [])
        if len(listed) < HISTORY:
            listed.append(
                Change(
                    before=change.before,
                    after=change.after,
                    actor=change.actor,
                    actor_label="",
                    at=change.at,
                )
            )
    names = await _labels(session, [c.actor for cs in changes.values() for c in cs])
    for cs in changes.values():
        for c in cs:
            c.actor_label = _label(c.actor, names)
    out = []
    for key, definition in DEFINITIONS.items():
        row = rows.get(key)
        out.append(
            SettingView(
                key=key,
                kind=definition.kind,
                label=definition.label,
                help=definition.help,
                minimum=definition.minimum,
                maximum=definition.maximum,
                value=row.value if row else default(settings, key),
                default=default(settings, key),
                overridden=row is not None,
                updated_by=row.updated_by if row else None,
                updated_at=row.updated_at if row else None,
                changes=changes.get(key, []),
            )
        )
    return out


def _known(key: str) -> None:
    if key not in DEFINITIONS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no setting {key!r}")


@router.get("")
async def list_settings(session: Session, _: Operator, settings: SettingsDep) -> list[SettingView]:
    return await _views(session, settings)


@router.put("/{key}")
async def set_setting(
    key: str, body: NewValue, session: Session, actor: Operator, settings: SettingsDep
) -> list[SettingView]:
    _known(key)
    try:
        value = normalize(settings, key, body.value)
    except SettingError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    row = await session.get(SystemSetting, key)
    before = row.value if row else None
    if row is None:
        session.add(SystemSetting(key=key, value=value, updated_by=actor.model_dump()))
    else:
        row.value = value
        row.updated_by = actor.model_dump()
    session.add(SystemSettingChange(key=key, before=before, after=value, actor=actor.model_dump()))
    await session.commit()
    LIVE.set(key, value)
    return await _views(session, settings)


@router.delete("/{key}")
async def reset_setting(
    key: str, session: Session, actor: Operator, settings: SettingsDep
) -> list[SettingView]:
    _known(key)
    row = await session.get(SystemSetting, key)
    if row is not None:
        session.add(
            SystemSettingChange(key=key, before=row.value, after=None, actor=actor.model_dump())
        )
        await session.delete(row)
        await session.commit()
    LIVE.set(key, None)
    return await _views(session, settings)
