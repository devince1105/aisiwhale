"""What people did in the back office (AD-06, D-234): one row a change, append-only.

Every request that changes something and comes through the back office's door (``Operator``:
an admin signed in, or the operator token) is written here by the API — who, when, which route
with which ids, what they sent (secrets masked), and how it ended — refused attempts too. It is
the "who did what" of the back office; what a change did to an entity's state is that entity's
own record (``state_transitions``, events)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, Index, func
from sqlalchemy.orm import Mapped, mapped_column

from autora.db.base import Base, IdMixin


class AdminAction(IdMixin, Base):
    __tablename__ = "admin_actions"
    __table_args__ = (
        Index("ix_admin_actions_created", "created_at"),
        Index("ix_admin_actions_company_created", "company_id", "created_at"),
        Index("ix_admin_actions_target", "target_type", "target_id"),
    )

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    actor: Mapped[dict[str, Any]]
    """``{"kind": "human", "id": "admin:<reader id>"}``, or ``operator`` for the token."""
    method: Mapped[str]
    route: Mapped[str]
    """The route's template: ``/api/articles/{article_id}/unpublish``."""
    action: Mapped[str]
    """What it is called in one word or two: the endpoint's name (``unpublish``)."""
    target_type: Mapped[str | None]
    """From the route's first id: ``article`` for ``{article_id}``."""
    target_id: Mapped[str | None]
    company_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("companies.id"))
    status: Mapped[int]
    """The response's status: 2xx done, 4xx refused."""
    input: Mapped[dict[str, Any]]
    """The query and the JSON body as sent; passwords, tokens and secrets masked, long text cut."""
    ip: Mapped[str | None]
