"""團隊群組 (D-109): the office's group chat — what the company's agents did, told as messages,
and what the operator writes back.

Nothing here is made up: every message is an event the company already recorded, of the kinds a
person would want to hear about (``chat_types()``) — a milestone of the work, an approval asked
for, a failure — and never the steps between (thinking, tool calls, polls). Each business adds
its own kinds (``hear``); this layer names none of them. The operator's own messages are events
too (``TEAM_MESSAGE_POSTED``), so the group reads the same for everyone and a bridge to Discord
later has one stream to follow.
"""

from __future__ import annotations

import uuid
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from autora.company.events import TeamMessagePosted
from autora.db.models import EventRecord
from autora.runtime.actor import Actor
from autora.runtime.events.outbox import emit, to_envelope
from autora.runtime.events.schema import EventEnvelope, new_event

CORE_TYPES: tuple[str, ...] = (
    "TEAM_MESSAGE_POSTED",
    "APPROVAL_REQUESTED",
    "APPROVAL_APPROVED",
    "APPROVAL_REJECTED",
    "APPROVAL_RETURNED",
    "APPROVAL_EXPIRED",
    "WORKFLOW_RUN_COMPLETED",
    "WORKFLOW_RUN_FAILED",
    "AGENT_RUN_FAILED",
    "TASK_BLOCKED",
    "BUDGET_EXHAUSTED",
    "POLICY_DENIED",
    "AGENT_CREATED",
    "AGENT_RETIRED",
    # a project stopped or started again (D-131): stopping the product is news to the operator
    "PROJECT_PAUSED",
    "PROJECT_RESUMED",
)
"""What the group hears about from the company itself. The web decides how each reads (and
skips a failure that will be retried); the list only keeps the steps between out of the feed."""

_heard: list[str] = []


def hear(*event_types: str) -> None:
    """A business adds what of its own the group hears about (its milestones, not its steps).
    Called when the business's package is imported, as its events register themselves."""
    _heard.extend(t for t in event_types if t not in _heard)


def chat_types() -> tuple[str, ...]:
    return CORE_TYPES + tuple(t for t in _heard if t not in CORE_TYPES)


FEED_LIMIT = 200


async def team_feed(
    session: AsyncSession, company_id: uuid.UUID, *, before: int | None = None, limit: int = 60
) -> tuple[list[EventEnvelope], bool]:
    """The group's latest ``limit`` messages before ``before`` (a seq), oldest first, and whether
    there are older ones."""
    stmt = select(EventRecord).where(
        EventRecord.company_id == company_id, EventRecord.event_type.in_(chat_types())
    )
    if before is not None:
        stmt = stmt.where(EventRecord.seq < before)
    rows = list(await session.scalars(stmt.order_by(EventRecord.seq.desc()).limit(limit + 1)))
    more = len(rows) > limit
    return [to_envelope(row) for row in reversed(rows[:limit])], more


async def post_message(
    session: AsyncSession,
    *,
    company_id: uuid.UUID,
    text: str,
    actor: Actor,
    kind: Literal["note", "brief"] = "note",
    ref_type: str | None = None,
    ref_id: uuid.UUID | None = None,
) -> EventEnvelope:
    """The operator's message, as the company's event: into the stream, the office and the log."""
    envelope = new_event(
        TeamMessagePosted(text=text.strip()[:1000], kind=kind, ref_type=ref_type, ref_id=ref_id),
        company_id=company_id,
        actor=actor,
        aggregate_type="company",
        aggregate_id=company_id,
    )
    return await emit(session, envelope)
