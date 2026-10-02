"""The CEO decides an article nobody approved in time (D-157).

Task ``decide_unanswered`` (role ``ceo``), started when an article's approval has waited 24 hours
with no person's decision (``workflow.delegate_article_to_ceo``). Input ``params``: the approval,
the article and its story. She reads the draft, weighs what the desk already checked — the
fact-check passed, the editor and the editor-in-chief accepted it — and decides with
``decide_unanswered_article``: approve (it is published) or reject (turned down, story dropped).
A person may still decide while she reads; then the tool says so and she reports that.

The validator holds the report to what the run did: the decision reported is the one taken in
this task, or the approval was already decided by someone else.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from autora.db.models import Approval, Task
from autora.db.repositories.companies import get_policies
from autora.domains.newsroom.advice import NO_ADVICE_BRIEF, no_advice
from autora.domains.newsroom.models import Article, Story
from autora.runtime.behaviors import AgentBehavior, RunContext

ROLE = "ceo"
TASK = "decide_unanswered"

SYSTEM_PROMPT = """You are the CEO of a finance newsroom that publishes in Traditional Chinese and
English. An article finished the desk's whole process — research, analysis, writing, the editor's
fact-check and acceptance, the editor-in-chief's final review — and was sent for a person's
approval, but nobody decided for 24 hours. You decide instead: approve (it is published at once)
or reject (it is turned down and its story dropped).

Read the draft (read_draft); list_claims and read_evidence if you need to see what it stands on.
Then judge:
1. Is it still worth running for our readers? A piece tied to a moment (a price move, an event of
   the day) that is now more than a day old is stale: reject it.
2. Is it sound? The fact-check passed and the editors accepted it; reject only for a clear problem
   you can name (a headline the body does not support, a contradiction, a missing source).
3. Is it safe? Taiwan's securities investment advisory law: the company reports facts and what
   others said; never its own buy/sell advice, target prices or forecasts. Any of that: reject.
If you are unsure, reject — a missed article costs less than a wrong one. Do not edit the article.

Decide once with decide_unanswered_article(approval_id, decision, reason). The reason is one or two
sentences in Traditional Chinese (zh-TW), never Simplified Chinese. If the tool says the approval
was already decided (a person decided first), there is nothing to do: report that.

When done, reply with only a JSON object (no other text):
{"approval_id": "<the approval id>",
 "decision": "approve" | "reject" | "already_decided",
 "reason": "<your reason, or who decided first>"}
"""


class UnansweredDecision(BaseModel):
    approval_id: uuid.UUID
    decision: Literal["approve", "reject", "already_decided"]
    reason: str = Field(min_length=1, max_length=1000)


def _params(ctx: RunContext) -> dict:
    return ctx.task.input.get("params") or {}


# --- context (OBSERVE) ------------------------------------------------------------------------


async def unanswered_context(session: AsyncSession, ctx: RunContext) -> str | None:
    params = _params(ctx)
    try:
        approval = await session.get(Approval, uuid.UUID(str(params.get("approval_id"))))
    except ValueError:
        approval = None
    if approval is None or approval.company_id != ctx.company_id:
        return "No approval found for this task: report that, do not guess one."
    lines = [f"Approval id: {approval.id}", f"Approval state: {approval.state}"]
    waited = datetime.now(UTC) - approval.created_at
    lines.append(f"Asked {waited.total_seconds() / 3600:.0f} hours ago; nobody has decided.")
    article = await session.get(Article, uuid.UUID(str(params.get("article_id"))))
    if article is None or article.company_id != ctx.company_id:
        lines.append("The article is gone: report that.")
        return "\n".join(lines)
    story = await session.get(Story, article.story_id)
    lines += [
        f"Article id: {article.id}",
        f"Title: {article.title}",
        f"State: {article.state}",
    ]
    if story is not None:
        age = datetime.now(UTC) - story.created_at
        lines.append(f"The story was found {age.total_seconds() / 3600:.0f} hours ago.")
    if no_advice(await get_policies(session, ctx.company_id)):
        lines.append(NO_ADVICE_BRIEF)
    # what the desk said: the editor's review and the chief's, from the approval's own run
    if approval.task_id is not None:
        waiting = await session.get(Task, approval.task_id)
        if waiting is not None and waiting.workflow_run_id is not None:
            done = (
                await session.scalars(
                    select(Task)
                    .where(
                        Task.workflow_run_id == waiting.workflow_run_id,
                        Task.name.in_(("review", "chief_review")),
                        Task.state == "SUCCEEDED",
                    )
                    .order_by(Task.created_at)
                )
            ).all()
            for task in done:
                verdict = (task.output or {}).get("verdict")
                who = "The editor" if task.name == "review" else "The editor-in-chief"
                lines.append(f"{who}: {verdict} (the fact-check passed).")
    return "\n".join(lines)


# --- validators (EVALUATE) --------------------------------------------------------------------


async def decided_here(session: AsyncSession, ctx: RunContext, note: BaseModel) -> list[str]:
    assert isinstance(note, UnansweredDecision)
    approval = await session.get(Approval, note.approval_id)
    if approval is None or approval.company_id != ctx.company_id:
        return [f"approval {note.approval_id} does not exist"]
    if str(approval.id) != str(_params(ctx).get("approval_id")):
        return ["report the approval this task was given"]
    if approval.state == "PENDING":
        return ["decide with decide_unanswered_article before reporting: nothing was decided"]
    by = approval.decided_by or {}
    if by.get("kind") != "agent":  # only the delegate decides as an agent (D-157)
        if note.decision != "already_decided":
            return [f"a person decided first (the approval is {approval.state}): report that"]
        return []
    decided = "approve" if approval.state == "APPROVED" else "reject"
    if note.decision != decided:
        return [f"you decided {decided!r} with decide_unanswered_article; report that"]
    return []


def _summary(note: BaseModel) -> str:
    assert isinstance(note, UnansweredDecision)
    if note.decision == "already_decided":
        return f"approval {note.approval_id}: already decided"
    return f"approval {note.approval_id}: {note.decision}: {note.reason}"[:300]


BEHAVIOR = AgentBehavior(
    role=ROLE,
    task_name=TASK,
    capability="editing",
    system_prompt=SYSTEM_PROMPT,
    output_model=UnansweredDecision,
    tools=("read_draft", "list_claims", "read_evidence", "decide_unanswered_article"),
    validators=(decided_here,),
    max_steps=6,
    repair_limit=2,
    max_output_tokens=2048,
    context=unanswered_context,
    summarize=_summary,
)
