"""Marketing's cover (D-142): a photo for the article, found while it is being drafted.

Task ``cover`` (role ``marketing``), input ``params.story_id``, after the analysis and alongside
the draft, so the person approving the article sees it. Marketing searches the free photo library
(``search_images``) with a few English words for the story's subject and makes the best result
the cover (``set_cover``), which stores it at 1200x630. It reports ``CoverNote``: the photo, or
that there is none — no cover is better than a misleading one, and never a reason to hold the
article.

The photo illustrates the subject (a wafer for a chip story, a trading screen for a market one);
it is not news photography. So it must not look like it shows a real, named person, company or
event: a stock photo passed off as "the CEO" or "the factory" misleads.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from autora.domains.newsroom.agents.marketing import ROLE
from autora.domains.newsroom.agents.researcher import task_story_id
from autora.domains.newsroom.covers import cover_of
from autora.domains.newsroom.models import Claim, CoverState, Story
from autora.runtime.behaviors import AgentBehavior, RunContext

TASK = "cover"
CLAIMS = 6

SYSTEM_PROMPT = """You are the marketing editor of a bilingual finance newsroom. Pick the cover
photo for the article about the story below, from a free photo library.

1. search_images with two to four plain English words for what the story is about, as a
   picture: the thing, not the news ("processor chip", "ai chip", "stock market chart", "container
   port", "gold bars", "banknotes"). Words with another everyday meaning find that instead
   ("wafer" finds cookies). Each result has the library's tags ("shows") and, when a viewer looked
   at it, what the image actually looks like ("looks": style, dated, any text or logo, quality) —
   trust "looks" over the tags, and skip what does not fit.
2. Choose the one that fits best and set_cover it, with what it shows in Traditional Chinese and
   in English (one short sentence each, describing the image, not the news).
The free library comes first, always: a library image that fits is better than any generated
one. Try different words before giving up on it.
3. Nothing fits after three searches (or what fits is another article's already): generate_cover
   with an English prompt for an image that fits — the subject as a picture, composition, colour
   and mood (e.g. "a sleek dark-blue 3D dashboard of portfolio holdings, glowing bar charts and
   pie segments floating above a glass desk"). It costs more than a library photo, so only then.
   Coins and tokens in a prompt are plain: never a cryptocurrency's symbol (a stablecoin story is
   not Bitcoin's or Ethereum's). If its "looks" shows text, a logo, a crypto symbol or a person,
   or it does not fit, generate once more; if
   generation is not available, report no cover.

Look: current and clean, like a finance site's lead image today. For technology, chips and AI,
prefer a modern 3D illustration (a glowing processor, a chip on a dark circuit) over a photo of
an old circuit board with through-hole parts; skip anything that reads as dated (vintage, retro,
old electronics), icons, clip art, cartoons, flat illustrations of people, chart-icon grids and
images with words in them. None of the results fit: search again with other words.

A company's own logo or product may be shown when the story is about that company (reporting on
it is editorial use). Never another company's brand, and never a photo that would pass for a real
person or a specific event of the story (a stranger in a suit as "the CEO", any factory as
"TSMC's fab"): skip one whose description names a person, or a company or brand the story is not
about. Prefer objects, places and charts over faces.

When done, reply with only a JSON object (no other text):
{"story_id": "<the story id>", "photo_id": "<from set_cover, or null>",
 "reason": "<one sentence: why this photo, or why none>"}
"""


class CoverNote(BaseModel):
    story_id: uuid.UUID
    photo_id: str | None = None
    reason: str = Field(min_length=1, max_length=400)


async def cover_context(session: AsyncSession, ctx: RunContext) -> str | None:
    story_id = task_story_id(ctx)
    story = await session.get(Story, story_id) if story_id else None
    if story is None or story.company_id != ctx.company_id:
        return "No story found for this task: report that, do not guess one."
    lines = [f"Story id: {story.id}", f"Story: {story.title}"]
    if story.summary:
        lines.append(f"Summary: {story.summary}")
    if story.angle:
        lines.append(f"Angle: {story.angle}")
    claims = (
        await session.scalars(
            select(Claim.text).where(Claim.story_id == story.id).order_by(Claim.id).limit(CLAIMS)
        )
    ).all()
    if claims:
        lines.append("What the article will say:")
        lines += [f"- {text[:200]}" for text in claims]
    existing = await cover_of(session, story.id)
    if (ctx.task.input.get("params") or {}).get("generate"):
        # a person's request (D-145): the cover it has is replaced, and kept to swap back to
        lines.append(
            "A person asked for a generated cover for this story: skip the library and "
            "generate_cover (it replaces the cover it has)."
        )
    elif existing is not None and existing.state == CoverState.REMOVED:
        lines.append("A person took this story's cover off: report no cover, do not search.")
    elif existing is not None:
        lines.append(
            f"It already has a cover (photo {existing.provider_id}, found with "
            f"{existing.query!r}): report that photo, do not search again."
        )
    return "\n".join(lines)


async def note_matches_the_cover(
    session: AsyncSession, ctx: RunContext, note: BaseModel
) -> list[str]:
    assert isinstance(note, CoverNote)
    story_id = task_story_id(ctx)
    if story_id is None or note.story_id != story_id:
        return [f"story_id must be this task's story: {story_id}"]
    row = await cover_of(session, story_id)
    shown = row.provider_id if row is not None and row.state == CoverState.ACTIVE else None
    if note.photo_id is None and shown is not None:
        return [f"the story's cover is photo {shown}: report it"]
    if note.photo_id is not None and note.photo_id != shown:
        return [
            f"photo {note.photo_id} is not the story's cover"
            + (f" ({shown} is)" if shown else ": call set_cover first, or report none")
        ]
    return []


def _summary(note: BaseModel) -> str:
    assert isinstance(note, CoverNote)
    return f"cover: photo {note.photo_id}" if note.photo_id else f"no cover: {note.reason[:120]}"


BEHAVIOR = AgentBehavior(
    role=ROLE,
    task_name=TASK,
    capability="drafting",
    system_prompt=SYSTEM_PROMPT,
    output_model=CoverNote,
    tools=("search_images", "set_cover", "generate_cover"),
    validators=(note_matches_the_cover,),
    max_steps=8,
    repair_limit=2,
    max_output_tokens=1024,
    context=cover_context,
    summarize=_summary,
)
