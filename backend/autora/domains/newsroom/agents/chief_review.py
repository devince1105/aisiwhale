"""The editor-in-chief's final review (D-110): the last word on a piece before a person approves.

Task ``chief_review`` (role ``editor_in_chief``), input ``params.story_id``, after the editor
accepted the draft. The chief reads the draft and the editor's review and decides with
``final_review``: accept (on to a person's approval), revise (back to the writer, and through
the editor again, within the article's revisions) or veto (the piece is turned down and its story
dropped; the workflow stops there — ``workflow.CHIEF_HALT``). It reports a ``ChiefReview``.

The chief judges what the editor does not: whether the piece is worth running, its headline and
direction, and whether it keeps the company's policy (no advice). The editor has already checked
the facts against their sources; the chief does not redo that.

The validators hold the report to what the run did: the decision was taken in this task on this
story's article, the verdict and ``dropped`` are the ones taken, a revision lists its issues and
a veto its reason.
"""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from autora.db.models import EventRecord, Task
from autora.db.repositories.companies import get_policies
from autora.domains.newsroom.advice import NO_ADVICE_BRIEF, no_advice
from autora.domains.newsroom.agents.editor import PERSON_SENT_BACK, person_sent_back
from autora.domains.newsroom.agents.researcher import task_story_id
from autora.domains.newsroom.models import (
    Article,
    ArticleAccess,
    ArticleState,
    ArticleVersion,
    Story,
)
from autora.domains.newsroom.policy import vip_guidelines
from autora.domains.newsroom.review import MAX_REVISIONS
from autora.domains.newsroom.tools.review import Issue
from autora.runtime.behaviors import AgentBehavior, RunContext

ROLE = "editor_in_chief"
TASK = "chief_review"

SYSTEM_PROMPT = """You give the final editorial review of a finance newsroom's article
(Traditional Chinese and English) before a person approves it for publication. The editor has
already checked every fact against its sources and accepted the draft; do not redo that.

Judge what the editor does not:
1. Is it worth running for this company's readers — a clear, current angle, not a thin or stale
   one?
2. The headline and the lead: accurate to the body, specific (a named period, a named company),
   not sensational.
3. Direction and balance: contested points written as who says what; the company's policy on
   advice kept (it reports facts and what others said, never its own buy/sell advice or price
   forecast).

Read the draft (read_draft); list_claims and read_evidence if you need to see what it stands on.
Then decide with final_review(article_id, verdict, issues, reason, vip):
- accept: it can go to a person for approval. Also decide vip: true makes it VIP — members read
  all of it, everybody else only its opening — following the company's VIP guidelines below;
  most articles are free;
- revise: something must change first — each issue says what and why (language and block when it
  is about one). This uses one of the article's revisions; with none left it drops the story;
- veto: the piece must not run at all — give the reason. Keep this for a piece that cannot be
  fixed (not worth covering, or against policy), not for wording.
Most drafts that reach you are sound: accept them.

When done, reply with only a JSON object (no other text):
{"article_id": "<the article id>",
 "verdict": "accept" | "revise" | "veto",
 "issues": [{"message": "...", "kind": "fact|unsupported|missing_context|translation|style|other",
             "lang": "zh-TW|en (optional)", "block_ref": "3 (optional)"}],
 "reason": "<for veto: why>",
 "vip": <for accept: true if you made it VIP>,
 "dropped": <true if final_review said the article was turned down>}
Write the issues and the reason in Traditional Chinese (zh-TW); never Simplified Chinese.
"""


class ChiefReview(BaseModel):
    article_id: uuid.UUID
    verdict: Literal["accept", "revise", "veto"]
    issues: list[Issue] = Field(default=[], max_length=20)
    reason: str | None = Field(default=None, max_length=1000)
    vip: bool = False
    """For accept (D-159): made VIP, for members."""
    dropped: bool = False
    """The piece was turned down (a veto, or a revision with none left): the workflow stops."""


# --- context (OBSERVE) ------------------------------------------------------------------------


async def final_review_context(session: AsyncSession, ctx: RunContext) -> str | None:
    story_id = task_story_id(ctx)
    story = await session.get(Story, story_id) if story_id else None
    if story is None or story.company_id != ctx.company_id:
        return "No story found for this task: report that, do not guess one."
    lines = [f"Story: {story.title}", f"Story id: {story.id}"]
    policies = await get_policies(session, ctx.company_id)
    if no_advice(policies):
        lines.append(NO_ADVICE_BRIEF)
    lines.append(f"The company's VIP guidelines (for accept): {vip_guidelines(policies)}")
    article = await session.scalar(select(Article).where(Article.story_id == story.id))
    if article is None:
        lines.append("This story has no article: report that.")
        return "\n".join(lines)
    versions = (
        await session.scalars(
            select(ArticleVersion)
            .where(ArticleVersion.draft_group_id == article.current_draft_group_id)
            .order_by(ArticleVersion.id)
        )
    ).all()
    lines += [
        f"Article id: {article.id}",
        f"Draft: version {versions[0].version if versions else '?'} "
        f"({', '.join(v.lang for v in versions)}); state {article.state}",
        f"Revisions so far: {article.revision_count} of {MAX_REVISIONS}",
    ]
    if article.revision_count >= MAX_REVISIONS:
        lines.append("No revisions left: sending it back drops the story.")
    asked = await person_sent_back(session, ctx)
    if asked:
        lines.append(PERSON_SENT_BACK.format(reason=asked))
    if article.published_group_id is not None:
        lines.append("This is a revision of a published article: a veto keeps the published one.")
    # the editor's review, from the task this one follows
    upstream = (
        (await session.scalars(select(Task).where(Task.id.in_(ctx.task.depends_on)))).all()
        if ctx.task.depends_on
        else []
    )
    review = next((t.output for t in upstream if t.output and "verdict" in t.output), None)
    if review:
        lines.append(f"The editor's review: {review.get('verdict')} (the fact-check passed).")
    return "\n".join(lines)


# --- validators (EVALUATE) --------------------------------------------------------------------


async def _decisions(session: AsyncSession, ctx: RunContext, article_id: uuid.UUID) -> list[dict]:
    rows = await session.scalars(
        select(EventRecord.payload)
        .where(EventRecord.task_id == ctx.task.id, EventRecord.event_type == "ARTICLE_REVIEWED")
        .order_by(EventRecord.id)
    )
    return [p for p in rows if p["article_id"] == str(article_id) and p.get("by_role") == ROLE]


async def decided_here(session: AsyncSession, ctx: RunContext, note: BaseModel) -> list[str]:
    assert isinstance(note, ChiefReview)
    story_id = task_story_id(ctx)
    article = await session.get(Article, note.article_id)
    if article is None or article.company_id != ctx.company_id:
        return [f"article {note.article_id} does not exist"]
    if story_id is not None and article.story_id != story_id:
        return [f"article {note.article_id} is not this task's story's article"]
    decisions = await _decisions(session, ctx, note.article_id)
    if not decisions:
        return ["decide with final_review before reporting: nothing was decided"]
    taken = decisions[-1]["verdict"]
    if taken != note.verdict:
        return [f"you decided {taken!r} with final_review; report that verdict"]
    if note.verdict == "revise" and not note.issues:
        return ["a revision lists at least one issue: the ones you sent with final_review"]
    if note.verdict == "veto" and not (note.reason or "").strip():
        return ["a veto says why (reason)"]
    is_vip = article.access == ArticleAccess.MEMBERS.value
    if note.verdict == "accept" and note.vip != is_vip:
        return [f"vip is {str(is_vip).lower()}: report what you set with final_review"]
    turned_down = article.state == ArticleState.REJECTED or (
        article.published_group_id is not None and note.verdict != "accept"
        and article.state != ArticleState.DRAFT
    )  # fmt: skip
    if note.dropped != turned_down:
        return [f"dropped is {str(turned_down).lower()}: the article is now {article.state}"]
    return []


def _summary(note: BaseModel) -> str:
    assert isinstance(note, ChiefReview)
    if note.verdict == "accept":
        return f"final review: accepted article {note.article_id}"
    if note.verdict == "veto":
        return f"final review: vetoed article {note.article_id}"
    return f"final review: sent article {note.article_id} back ({len(note.issues)} issues)"


BEHAVIOR = AgentBehavior(
    role=ROLE,
    task_name=TASK,
    capability="editing",
    system_prompt=SYSTEM_PROMPT,
    output_model=ChiefReview,
    tools=("read_draft", "list_claims", "read_evidence", "final_review"),
    validators=(decided_here,),
    max_steps=8,
    repair_limit=2,
    max_output_tokens=4096,
    context=final_review_context,
    summarize=_summary,
)
