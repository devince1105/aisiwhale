"""D-135: a stored event this process cannot validate (a newer worker's event type) is left out
of reads — the snapshot, the team feed, the event listing and the live stream — not fatal."""

import logging
import uuid
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError
from sqlalchemy import insert, select

from autora.company import team_chat
from autora.company.events import GoalCreated
from autora.company.team_chat import team_feed
from autora.db.models import EventRecord
from autora.realtime.gateway import EventHub
from autora.realtime.projection import begin_consistent_read, load_snapshot
from autora.runtime.actor import Actor
from autora.runtime.events import new_event
from autora.runtime.events.outbox import (
    emit,
    load_event_page,
    read_envelope,
    to_envelope,
)
from tests.conftest import unique_company
from tests.realtime.test_gateway import FakeSocket

UNKNOWN = "FROM_A_NEWER_WORKER"
SYSTEM = Actor.system("test")


async def _goal(session, company_id) -> int:
    event = await emit(
        session,
        new_event(
            GoalCreated(title="g", level="cycle", metric="m", target=1),
            company_id=company_id, actor=SYSTEM, aggregate_type="goal",
            aggregate_id=uuid.uuid4(),
        ),
    )  # fmt: skip
    return event.seq


async def _unknown(session, company_id) -> int:
    """A row as a newer worker would write it: a valid envelope with a type this code lacks."""
    return await session.scalar(
        insert(EventRecord)
        .values(
            id=uuid.uuid4(),
            event_type=UNKNOWN,
            schema_version=1,
            company_id=company_id,
            occurred_at=datetime.now(UTC),
            aggregate_type="company",
            aggregate_id=company_id,
            actor=SYSTEM.as_json(),
            payload={"hours": 66},
        )
        .returning(EventRecord.seq)
    )


@pytest.fixture
async def mixed_company(committed):
    """known, unknown, known — committed."""
    async with committed() as session:
        company = await unique_company(session, "unknown-ev")
        seqs = [
            await _goal(session, company.id),
            await _unknown(session, company.id),
            await _goal(session, company.id),
        ]
        await session.commit()
    return company.id, seqs


async def test_the_snapshot_leaves_it_out_and_warns_once(committed, mixed_company, caplog):
    company_id, (first, unknown, last) = mixed_company
    caplog.set_level(logging.WARNING, logger="autora.runtime.events.outbox")
    for _ in range(2):
        async with committed() as session:
            await begin_consistent_read(session)
            snapshot = await load_snapshot(session, company_id)
        assert [e.seq for e in snapshot.recent_events] == [first, last]
        assert snapshot.last_seq == last, "the head still counts the skipped row"
    warnings = [r.getMessage() for r in caplog.records if UNKNOWN in r.getMessage()]
    assert len(warnings) == 1, "once per event, not per request"
    assert f"seq {unknown}" in warnings[0]


async def test_the_team_feed_leaves_it_out(db_session, monkeypatch):
    """Even when the group is told to hear about the type (a business's ``hear``)."""
    monkeypatch.setattr(team_chat, "_heard", [*team_chat._heard, UNKNOWN])
    company = await unique_company(db_session, "unknown-feed")
    await _unknown(db_session, company.id)
    note = await team_chat.post_message(
        db_session, company_id=company.id, text="早安", actor=Actor.human("op")
    )
    items, more = await team_feed(db_session, company.id)
    assert [e.seq for e in items] == [note.seq] and not more


async def test_event_pages_move_past_it(db_session):
    company = await unique_company(db_session, "unknown-page")
    first = await _goal(db_session, company.id)
    unknown = await _unknown(db_session, company.id)
    last = await _goal(db_session, company.id)

    page, next_after, more = await load_event_page(db_session, company.id, limit=2)
    assert ([e.seq for e in page], next_after, more) == ([first], unknown, True)
    page, next_after, more = await load_event_page(
        db_session, company.id, after_seq=next_after, limit=2
    )
    assert ([e.seq for e in page], next_after, more) == ([last], last, False)


async def test_strict_where_it_matters(db_session):
    """Only reads are tolerant: building an envelope directly still refuses the type, so
    nothing can be emitted with it."""
    company = await unique_company(db_session, "unknown-strict")
    seq = await _unknown(db_session, company.id)
    row = await db_session.scalar(select(EventRecord).where(EventRecord.seq == seq))
    assert read_envelope(row) is None
    with pytest.raises(ValidationError, match="unknown event type"):
        to_envelope(row)


async def test_the_stream_skips_it_in_backlog_and_live(db_engine, committed, mixed_company):
    company_id, (first, _unknown_seq, last) = mixed_company
    hub = EventHub(engine=db_engine, session_factory=committed, poll_interval=30)
    await hub.start()
    try:
        socket = FakeSocket()
        await hub.connect(company_id, socket, since=first - 1)
        assert socket.event_seqs() == [first, last]
        assert socket.of("BACKLOG_DONE")[0]["head_seq"] == last

        async with committed() as session:
            skipped = await _unknown(session, company_id)
            after = await _goal(session, company_id)
            await session.commit()
        await socket.wait_for(lambda ms: any(m.get("seq") == after for m in ms))
        assert socket.event_seqs() == [first, last, after]
        assert skipped not in socket.event_seqs()
    finally:
        await hub.stop()
