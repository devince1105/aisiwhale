"""News Intelligence (D-110): what is happening in the markets now — the first desk of the day.

Task ``brief`` (role ``news_intelligence``), the first node of the desk's daily planning
(``planning.BRIEFED_PLAN_TEMPLATE``); the editor-in-chief's plan depends on it and reads its
output. It reads what the newsroom has already gathered — the stories the sources' items were
clustered into, and the week's classified headlines about the strip's stocks (D-091) — and says
what matters: the market moves, which candidate stories count and why, what to watch. No tools:
it searches nothing and commissions nothing; choosing is the chief's.

The validator holds it to the record: every story it names is one of this newsroom's candidates.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from autora.db.repositories.companies import get_policies
from autora.domains.newsroom.advice import NO_ADVICE_BRIEF, no_advice
from autora.domains.newsroom.models import StockHeadline, Story, StoryState
from autora.runtime.behaviors import AgentBehavior, RunContext

ROLE = "news_intelligence"
TASK = "brief"
CANDIDATES = 12
HEADLINES = 30
RECENT = timedelta(hours=36)


class MarketMove(BaseModel):
    what: str = Field(min_length=2, max_length=300)
    why: str = Field(min_length=2, max_length=400)


class StoryNote(BaseModel):
    story_id: uuid.UUID
    why_it_matters: str = Field(min_length=2, max_length=400)


class MarketBrief(BaseModel):
    """What is happening in the markets, for the chief's plan."""

    summary: str = Field(min_length=4, max_length=1500)
    market_moves: list[MarketMove] = Field(default=[], max_length=8)
    stories: list[StoryNote] = Field(default=[], max_length=CANDIDATES)
    """The candidate stories that matter today, most important first."""
    watch: list[str] = Field(default=[], max_length=5)
    """What to keep an eye on: coming data, decisions, developing stories."""


SYSTEM_PROMPT = """Each morning you brief a finance newsroom's editor-in-chief on what is
happening in the markets: international markets, policy, central banks and major events.

You are given what the newsroom's sources gathered — candidate stories, clustered from the
sources' items — and the latest headlines about the stocks it follows, each with its tone.
Everything you know is in it: do not add events, numbers or names it does not contain.

Say, in Traditional Chinese (zh-TW, never Simplified Chinese):
- summary: what is moving the markets now, in a few sentences;
- market_moves: the notable moves or developments, each with why it matters;
- stories: which candidate stories matter today and why, most important first — only stories
  from the list, by their id;
- watch: what to keep an eye on next.
Report facts and what others said; never your own advice or a price forecast. The chief decides
what the desk covers — you do not choose.

Reply with only a JSON object (no other text):
{"summary": "...", "market_moves": [{"what": "...", "why": "..."}],
 "stories": [{"story_id": "<id from the list>", "why_it_matters": "..."}], "watch": ["..."]}
"""


async def brief_context(session: AsyncSession, ctx: RunContext) -> str | None:
    """OBSERVE: the candidate stories and the latest headlines about the followed stocks."""
    now = datetime.now(UTC)
    candidates = (
        await session.scalars(
            select(Story)
            .where(
                Story.company_id == ctx.company_id,
                Story.state.in_([StoryState.DISCOVERED.value, StoryState.SELECTED.value]),
            )
            .order_by(Story.last_item_at.desc(), Story.score.desc())
            .limit(CANDIDATES)
        )
    ).all()
    lines = [f"Now: {now:%Y-%m-%d %H:%M} UTC"]
    if no_advice(await get_policies(session, ctx.company_id)):
        lines.append(NO_ADVICE_BRIEF)
    lines.append("Candidate stories (newest first):")
    if candidates:
        for story in candidates:
            lines.append(
                f"- {story.id} · {story.title} · {story.sources_count} source(s) · "
                f"last seen {story.last_item_at:%Y-%m-%d %H:%M}"
                + (f" · {story.summary[:160]}" if story.summary else "")
            )
    else:
        lines.append("- none: the sources brought nothing new")
    headlines = (
        await session.scalars(
            select(StockHeadline)
            .where(
                StockHeadline.published_at >= now - RECENT,
                StockHeadline.sentiment.is_not(None),
            )
            .order_by(StockHeadline.published_at.desc())
            .limit(HEADLINES)
        )
    ).all()
    if headlines:
        lines.append("")
        lines.append("Latest headlines about the followed stocks (tone toward the company):")
        for h in headlines:
            lines.append(f"- [{h.stock_key}] {h.title} · {h.sentiment} · {h.source}")
    return "\n".join(lines)


async def stories_are_candidates(
    session: AsyncSession, ctx: RunContext, output: BaseModel
) -> list[str]:
    """Every story the brief names is one of this newsroom's, and still a candidate."""
    assert isinstance(output, MarketBrief)
    ids = [note.story_id for note in output.stories]
    if not ids:
        return []
    found = {
        story.id: story
        for story in (
            await session.scalars(
                select(Story).where(Story.company_id == ctx.company_id, Story.id.in_(ids))
            )
        ).all()
    }
    issues = []
    for story_id in ids:
        story = found.get(story_id)
        if story is None:
            issues.append(
                f"story {story_id} is not one of this newsroom's: use an id from the list"
            )
        elif story.state not in (StoryState.DISCOVERED.value, StoryState.SELECTED.value):
            issues.append(f"{story.title!r} is already {story.state}: it is not a candidate")
    return issues


def _summary(output: BaseModel) -> str:
    assert isinstance(output, MarketBrief)
    return f"market brief: {len(output.stories)} story(ies) flagged; {output.summary[:120]}"


BEHAVIOR = AgentBehavior(
    role=ROLE,
    task_name=TASK,
    capability="reasoning",
    system_prompt=SYSTEM_PROMPT,
    output_model=MarketBrief,
    tools=(),
    validators=(stories_are_candidates,),
    max_steps=3,
    repair_limit=2,
    max_output_tokens=4096,
    context=brief_context,
    summarize=_summary,
)
