"""Who may do what in the back office (AD-09, D-234 ①): a role a person, beyond ADMIN_EMAILS.

The addresses on ADMIN_EMAILS are owners, from the environment; anybody else an owner lets in
has a row here with one of four roles. The permissions each role has are the API's
(``autora_api.permissions``), not stored: a role means the same thing everywhere."""

from __future__ import annotations

import uuid
from enum import StrEnum
from typing import Any

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from autora.db.base import Base, TimestampMixin, check_in


class AdminRoleName(StrEnum):
    OWNER = "owner"
    EDITOR = "editor"
    FINANCE = "finance"
    VIEWER = "viewer"


class AdminRole(TimestampMixin, Base):
    __tablename__ = "admin_roles"
    __table_args__ = (check_in("role", AdminRoleName),)

    reader_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("readers.id"), primary_key=True)
    role: Mapped[str]
    granted_by: Mapped[dict[str, Any]]
    """Who gave it (or last changed it): ``{"kind": "human", "id": "admin:<reader id>"}``."""
