"""Settings the back office changes while everything runs (AD-11, D-234).

``system_settings``: a value set in the back office for one of the keys ``runtime.live_settings``
defines; no row: the environment's (the deploy's default). ``system_setting_changes``: every
change, what it was before and after, by whom — append-only, as the audit trail is."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Index, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from autora.db.base import Base, IdMixin


class SystemSetting(Base):
    __tablename__ = "system_settings"

    key: Mapped[str] = mapped_column(primary_key=True)
    value: Mapped[Any] = mapped_column(JSONB, nullable=False)
    updated_by: Mapped[dict[str, Any]]
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class SystemSettingChange(IdMixin, Base):
    __tablename__ = "system_setting_changes"
    __table_args__ = (Index("ix_system_setting_changes_key_at", "key", "at"),)

    key: Mapped[str]
    before: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
    """None: it was the environment's."""
    after: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
    """None: back to the environment's."""
    actor: Mapped[dict[str, Any]]
    at: Mapped[datetime] = mapped_column(server_default=func.now())
