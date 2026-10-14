"""What the desk covers, in shares (D-253): which candidates the editor-in-chief is shown, and
whether one more story of a kind keeps the mix (``policy.topic_mix``).

A story's kind is worked out from what the site already knows of it: its section — the one a
person gave it, else the one most of its sources name, else the one its own words name (D-208,
D-212) — and its title and summary, against the focus terms. The mix is counted over the stories
the desk commissioned in the last ``WINDOW``: those whose article workflow started then.
"""

from __future__ import annotations

import uuid
from collections import Counter
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from autora.db.models import WorkflowRun
from autora.domains.newsroom.models import Source, SourceItem, Story, StoryItem
from autora.domains.newsroom.policy import Bucket, TopicMix
from autora.domains.newsroom.sources import SECTION, SECTION_GUESS, SECTIONS
from autora.domains.newsroom.workflow import TEMPLATE_NAME

WINDOW = timedelta(days=30)


async def story_sections(
    session: AsyncSession, stories: list[Story]
) -> dict[uuid.UUID, str | None]:
    """Each story's section: a person's, else its sources' most named, else its own words'."""
    ids = [s.id for s in stories]
    named = Source.config[SECTION].astext
    by_sources: dict[uuid.UUID, str] = {}
    if ids:
        rows = await session.execute(
            select(StoryItem.story_id, named, func.count())
            .join(SourceItem, SourceItem.id == StoryItem.source_item_id)
            .join(Source, Source.id == SourceItem.source_id)
            .where(StoryItem.story_id.in_(ids), named.in_(SECTIONS))
            .group_by(StoryItem.story_id, named)
            .order_by(StoryItem.story_id, func.count().desc(), named)
        )
        for story_id, section, _ in rows:
            by_sources.setdefault(story_id, section)
    out: dict[uuid.UUID, str | None] = {}
    for story in stories:
        seed = story.seed or {}
        given = seed.get(SECTION) if seed.get(SECTION) in SECTIONS else None
        guess = seed.get(SECTION_GUESS) if seed.get(SECTION_GUESS) in SECTIONS else None
        out[story.id] = given or by_sources.get(story.id) or guess
    return out


def story_text(story: Story) -> str:
    return " ".join(filter(None, [story.title, story.summary]))


async def buckets(
    session: AsyncSession, mix: TopicMix, stories: list[Story]
) -> dict[uuid.UUID, Bucket]:
    sections = await story_sections(session, stories)
    return {s.id: mix.bucket(section=sections[s.id], text=story_text(s)) for s in stories}


async def recent_mix(
    session: AsyncSession,
    mix: TopicMix,
    company_id: uuid.UUID,
    *,
    now: datetime | None = None,
) -> Counter[str]:
    """How many stories of each kind the desk commissioned in the last ``WINDOW``."""
    since = (now or datetime.now(UTC)) - WINDOW
    story_ids = (
        await session.scalars(
            select(WorkflowRun.params["story_id"].astext).where(
                WorkflowRun.company_id == company_id,
                WorkflowRun.template_name == TEMPLATE_NAME,
                WorkflowRun.created_at >= since,
            )
        )
    ).all()
    ids = {uuid.UUID(s) for s in story_ids if s}
    if not ids:
        return Counter()
    stories = list((await session.scalars(select(Story).where(Story.id.in_(ids)))).all())
    return Counter((await buckets(session, mix, stories)).values())
