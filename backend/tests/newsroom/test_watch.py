"""D-131: a newsroom quiet for a day is said once, with what the records show might be why."""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from autora.db.models import BusinessUnit, EventRecord, Project
from autora.domains.newsroom import organization
from autora.domains.newsroom.models import Article
from autora.domains.newsroom.organization import BUSINESS_UNIT
from autora.domains.newsroom.watch import quiet_newsroom, schedule_handler
from autora.runtime.actor import Actor


class _Schedule:
    def __init__(self, company_id):
        self.company_id = company_id


async def _unit(session, company_id):
    """The newsroom's business, with a project in it (the fixture has neither)."""
    await organization.build(session, company_id, actor=Actor.system("test"))
    unit = await session.scalar(
        select(BusinessUnit).where(
            BusinessUnit.company_id == company_id, BusinessUnit.key == BUSINESS_UNIT
        )
    )
    unit.created_at = datetime.now(UTC) - timedelta(days=3)
    project = await session.scalar(select(Project).where(Project.company_id == company_id))
    project.business_unit_id = unit.id
    await session.flush()
    return unit


async def test_quiet_for_a_day_is_said_once_with_its_causes(newsroom_room):
    room = newsroom_room
    drafted = await room.call("write_draft", room.draft(list(room.claims.values())))
    async with room.committed() as session:
        unit = await _unit(session, room.company.id)
        now = datetime.now(UTC)
        article = await session.get(Article, uuid.UUID(drafted.output["article_id"]))
        article.published_at = now - timedelta(hours=30)
        for project in (
            await session.scalars(select(Project).where(Project.business_unit_id == unit.id))
        ).all():
            project.kill_criteria = {"max_cost_usd": 10}
            project.state = "PAUSED"
        await session.flush()

        quiet = await quiet_newsroom(session, room.company.id, now=now)
        assert quiet is not None and quiet.hours == 30
        assert "project_paused" in quiet.causes and "no_work_started" in quiet.causes

        await schedule_handler()(session, _Schedule(room.company.id), now)
        said = (
            await session.scalars(
                select(EventRecord).where(
                    EventRecord.company_id == room.company.id,
                    EventRecord.event_type == "NEWSROOM_QUIET",
                )
            )
        ).all()
        assert len(said) == 1
        # said once a day: the next hour stays quiet
        assert await quiet_newsroom(session, room.company.id) is None


async def test_a_day_that_published_is_not_quiet(newsroom_room):
    room = newsroom_room
    drafted = await room.call("write_draft", room.draft(list(room.claims.values())))
    async with room.committed() as session:
        await _unit(session, room.company.id)
        article = await session.get(Article, uuid.UUID(drafted.output["article_id"]))
        article.published_at = datetime.now(UTC) - timedelta(hours=3)
        await session.flush()
        assert await quiet_newsroom(session, room.company.id) is None
