"""團隊群組 (D-109): the office's group chat — its messages, and the operator's own."""

from __future__ import annotations

import uuid
from typing import Annotated, Any, Literal

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from autora.app import build_embedder
from autora.company.team_chat import FEED_LIMIT, post_message, team_feed
from autora.db.models import Company
from autora.domains.newsroom.sources import SECTION
from autora.domains.newsroom.stories import StoryDesk
from autora_api.deps import Operator, RuntimeDep, Session
from autora_api.routers.newsroom import start_now
from autora_api.routers.public import Section

router = APIRouter(prefix="/api/companies/{company_id}/team", tags=["team"])


class TeamFeed(BaseModel):
    items: list[dict[str, Any]]
    """Event envelopes as JSON, oldest first (shape: frontend/event-schema EventEnvelope)."""
    has_more: bool
    """Older messages exist: ask again with ``before`` = the first item's seq."""


class TeamMessageIn(BaseModel):
    text: str = Field(min_length=1, max_length=1000)
    kind: Literal["note", "brief"] = "note"
    """``brief``: a story for the newsroom to write — taken up at once, as 開始製作 would."""
    section: Section | None = None
    """A brief's section on the site (D-208): a story started from a sentence has no sources to
    say where it belongs. Ignored for a note."""


class TeamMessageOut(BaseModel):
    seq: int | None
    story_id: uuid.UUID | None = None
    workflow_run_id: uuid.UUID | None = None


async def _company(session, company_id: uuid.UUID) -> Company:
    company = await session.get(Company, company_id)
    if company is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"company {company_id} not found")
    return company


@router.get("/feed")
async def get_feed(
    company_id: uuid.UUID,
    session: Session,
    _: Operator,
    before: Annotated[
        int | None, Query(ge=1, description="Only messages with seq < before")
    ] = None,
    limit: Annotated[int, Query(ge=1, le=FEED_LIMIT)] = 60,
) -> TeamFeed:
    """The group's latest messages (before ``before``), oldest first."""
    await _company(session, company_id)
    items, more = await team_feed(session, company_id, before=before, limit=limit)
    return TeamFeed(items=[e.model_dump(mode="json") for e in items], has_more=more)


@router.post("/messages", status_code=status.HTTP_201_CREATED)
async def post_team_message(
    company_id: uuid.UUID,
    body: TeamMessageIn,
    session: Session,
    operator: Operator,
    runtime: RuntimeDep,
) -> TeamMessageOut:
    """A note to the group, or a brief: a story started by hand from the text (its title, and
    the researcher's search), taken straight into production."""
    await _company(session, company_id)
    text = body.text.strip()
    if not text:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "the message is empty")
    story_id = run_id = None
    ref_type = None
    if body.kind == "brief":
        desk = StoryDesk(build_embedder(None))
        seed = {"query": text} | ({SECTION: body.section} if body.section else {})
        story = await desk.create(
            session, company_id=company_id, title=text, seed=seed, actor=operator
        )
        run = await start_now(session, story, None, operator, runtime)
        story_id, run_id, ref_type = story.id, run.id, "story"
    posted = await post_message(
        session,
        company_id=company_id,
        text=text,
        kind=body.kind,
        ref_type=ref_type,
        ref_id=story_id,
        actor=operator,
    )
    await session.commit()
    return TeamMessageOut(seq=posted.seq, story_id=story_id, workflow_run_id=run_id)
