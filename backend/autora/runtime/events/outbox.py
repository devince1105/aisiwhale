"""Persisting events: the transactional outbox (logs/3d-office/05_REALTIME_ARCHITECTURE.md §1).

``emit(session, envelope)`` writes the event in the caller's transaction, so the event exists
if and only if the state change commits. It also queues ``NOTIFY autora_events`` which Postgres
delivers only on commit.

Ordering guarantee: readers follow ``seq`` with a cursor (``seq > last_seq``). Sequence values
are assigned at insert time, so two concurrent transactions could otherwise commit out of seq
order and a reader could skip the smaller seq forever. ``emit`` takes a transaction-scoped
advisory lock per company before inserting, which makes commit order equal seq order within a
company. Keep event-emitting transactions short: the lock is held until commit.

Reading is tolerant, writing is strict: ``emit`` only takes a validated envelope, but a stored
row may be one this process cannot validate (a newer worker wrote an event type an older API
does not know yet). ``read_envelope``/``read_envelopes`` skip such rows and warn once per event,
so one unknown event never takes down the snapshot, the team feed or the live stream (D-135).
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Iterable, Sequence

from pydantic import ValidationError
from sqlalchemy import func, insert, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from autora.db.models import EventRecord
from autora.runtime.events.schema import EventEnvelope, Persistence, parse_event

EVENTS_CHANNEL = "autora_events"
EPHEMERAL_CHANNEL = "autora_ephemeral"
EPHEMERAL_MAX_BYTES = 7900  # NOTIFY payloads must stay under 8000 bytes
_LOCK_NAMESPACE = 0x41_55_54  # arbitrary int4 namespace for pg_advisory_xact_lock(int, int)
_SKIPPED_MAX = 10_000

log = logging.getLogger(__name__)
_skipped: set[uuid.UUID] = set()  # events already warned about


class EventEmitError(Exception):
    pass


async def emit(session: AsyncSession, envelope: EventEnvelope) -> EventEnvelope:
    """Append ``envelope`` to the event log. Returns a copy carrying the assigned ``seq``."""
    if envelope.persistence is Persistence.EPHEMERAL:
        raise EventEmitError(f"{envelope.event_type} is ephemeral; it is never written to the log")
    if envelope.seq is not None:
        raise EventEmitError(
            f"event {envelope.event_id} was already persisted (seq={envelope.seq})"
        )

    company = str(envelope.company_id)
    await session.execute(
        text("SELECT pg_advisory_xact_lock(:ns, hashtext(:company))"),
        {"ns": _LOCK_NAMESPACE, "company": company},
    )
    seq = await session.scalar(
        insert(EventRecord)
        .values(
            id=envelope.event_id,
            event_type=envelope.event_type,
            schema_version=envelope.schema_version,
            company_id=envelope.company_id,
            occurred_at=envelope.occurred_at,
            aggregate_type=envelope.aggregate_type,
            aggregate_id=envelope.aggregate_id,
            agent_id=envelope.agent_id,
            task_id=envelope.task_id,
            run_id=envelope.run_id,
            workflow_run_id=envelope.workflow_run_id,
            cycle_id=envelope.cycle_id,
            correlation_id=envelope.correlation_id,
            causation_id=envelope.causation_id,
            actor=envelope.actor.as_json(),
            payload=envelope.payload.model_dump(mode="json"),
        )
        .returning(EventRecord.seq)
    )
    await session.execute(select(func.pg_notify(EVENTS_CHANNEL, f"{company}:{seq}")))
    return envelope.model_copy(update={"seq": seq})


async def publish_ephemeral(session: AsyncSession, envelope: EventEnvelope) -> None:
    """Send an ephemeral event (progress, agent heartbeat) to live viewers. Never stored; the
    NOTIFY is delivered when the caller commits. Oversized payloads are refused."""
    if envelope.persistence is not Persistence.EPHEMERAL:
        raise EventEmitError(f"{envelope.event_type} is persisted; use emit()")
    data = envelope.model_dump_json(exclude={"seq"})
    if len(data.encode("utf-8")) > EPHEMERAL_MAX_BYTES:
        raise EventEmitError(f"{envelope.event_type} payload exceeds {EPHEMERAL_MAX_BYTES} bytes")
    await session.execute(select(func.pg_notify(EPHEMERAL_CHANNEL, data)))


def to_envelope(row: EventRecord) -> EventEnvelope:
    return parse_event(
        {
            "event_id": row.id,
            "seq": row.seq,
            "event_type": row.event_type,
            "schema_version": row.schema_version,
            "company_id": row.company_id,
            "occurred_at": row.occurred_at,
            "aggregate_type": row.aggregate_type,
            "aggregate_id": row.aggregate_id,
            "agent_id": row.agent_id,
            "task_id": row.task_id,
            "run_id": row.run_id,
            "workflow_run_id": row.workflow_run_id,
            "cycle_id": row.cycle_id,
            "correlation_id": row.correlation_id,
            "causation_id": row.causation_id,
            "actor": row.actor,
            "payload": row.payload,
        }
    )


def read_envelope(row: EventRecord) -> EventEnvelope | None:
    """``to_envelope`` for reading the log: ``None`` for a row this process cannot validate."""
    try:
        return to_envelope(row)
    except ValueError as error:  # pydantic's ValidationError is a ValueError
        if row.id not in _skipped:
            if len(_skipped) >= _SKIPPED_MAX:
                _skipped.clear()
            _skipped.add(row.id)
            log.warning(
                "skipped stored event %s (id %s, seq %s): %s",
                row.event_type,
                row.id,
                row.seq,
                _first_error(error),
            )
        return None


def read_envelopes(rows: Iterable[EventRecord]) -> list[EventEnvelope]:
    """The rows as envelopes, in order, leaving out the ones this process cannot validate."""
    return [envelope for row in rows if (envelope := read_envelope(row)) is not None]


def _first_error(error: ValueError) -> str:
    if isinstance(error, ValidationError) and error.errors():
        return error.errors()[0]["msg"]
    return str(error)


async def load_events(
    session: AsyncSession,
    company_id: uuid.UUID,
    *,
    after_seq: int = 0,
    until_seq: int | None = None,
    event_types: Sequence[str] | None = None,
    agent_id: uuid.UUID | None = None,
    run_id: uuid.UUID | None = None,
    correlation_id: uuid.UUID | None = None,
    limit: int = 200,
) -> list[EventEnvelope]:
    """Events of one company with ``after_seq < seq <= until_seq``, ordered by seq."""
    rows = await _event_rows(
        session, company_id, after_seq, until_seq, event_types, agent_id, run_id,
        correlation_id, limit,
    )  # fmt: skip
    return read_envelopes(rows)


async def load_event_page(
    session: AsyncSession,
    company_id: uuid.UUID,
    *,
    after_seq: int = 0,
    until_seq: int | None = None,
    event_types: Sequence[str] | None = None,
    agent_id: uuid.UUID | None = None,
    run_id: uuid.UUID | None = None,
    correlation_id: uuid.UUID | None = None,
    limit: int = 200,
) -> tuple[list[EventEnvelope], int, bool]:
    """One page of ``load_events``: the events, the seq to continue after and whether there are
    more. Paging follows the stored rows, so a skipped row neither ends nor repeats a page."""
    rows = await _event_rows(
        session, company_id, after_seq, until_seq, event_types, agent_id, run_id,
        correlation_id, limit + 1,
    )  # fmt: skip
    page = rows[:limit]
    return read_envelopes(page), page[-1].seq if page else after_seq, len(rows) > limit


async def _event_rows(
    session: AsyncSession,
    company_id: uuid.UUID,
    after_seq: int,
    until_seq: int | None,
    event_types: Sequence[str] | None,
    agent_id: uuid.UUID | None,
    run_id: uuid.UUID | None,
    correlation_id: uuid.UUID | None,
    limit: int,
) -> list[EventRecord]:
    stmt = select(EventRecord).where(
        EventRecord.company_id == company_id, EventRecord.seq > after_seq
    )
    if until_seq is not None:
        stmt = stmt.where(EventRecord.seq <= until_seq)
    if event_types:
        stmt = stmt.where(EventRecord.event_type.in_(event_types))
    if agent_id is not None:
        stmt = stmt.where(EventRecord.agent_id == agent_id)
    if run_id is not None:
        stmt = stmt.where(EventRecord.run_id == run_id)
    if correlation_id is not None:
        stmt = stmt.where(EventRecord.correlation_id == correlation_id)
    return list(await session.scalars(stmt.order_by(EventRecord.seq).limit(limit)))
