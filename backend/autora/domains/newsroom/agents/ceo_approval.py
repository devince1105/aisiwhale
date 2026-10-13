"""The CEO decides an article nobody approved in time (D-157).

Task ``decide_unanswered`` (role ``ceo``), started when an article's approval has waited with no
person's decision — within 8 hours, on her shift (D-252; ``workflow.handover_at``). Input
``params``: the approval, the article and its story. She reads the draft, weighs what the desk
already checked — the fact-check passed, the editor and the editor-in-chief accepted it — and
decides with ``decide_unanswered_article``: approve (it is published) or reject (turned down,
story dropped).
A person may still decide while she reads; then the tool says so and she reports that.

D-252: she publishes unless it breaks the advisory law or has an error she can name — the desk's
research is not to be thrown away for doubt. How old it is, she is told, against its section's
shelf life (``policy.shelf_life_hours``), counted from the story being found to the desk asking
for approval (the waiting for a decision is ours, not the article's): only past
``HARD_LIMIT_FACTOR`` shelf lives is it stale enough to turn down.

The validator holds the report to what the run did: the decision reported is the one taken in
this task, or the approval was already decided by someone else.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from autora.db.models import Approval, Task
from autora.db.repositories.companies import get_policies
from autora.domains.newsroom.advice import NO_ADVICE_BRIEF, no_advice
from autora.domains.newsroom.models import Article, Story
from autora.domains.newsroom.policy import HARD_LIMIT_FACTOR, shelf_life_hours
from autora.domains.newsroom.site import section_of
from autora.runtime.behaviors import AgentBehavior, RunContext

ROLE = "ceo"
TASK = "decide_unanswered"

SYSTEM_PROMPT = """You are the CEO of a finance newsroom that publishes in Traditional Chinese and
English. An article finished the desk's whole process — research, analysis, writing, the editor's
fact-check and acceptance, the editor-in-chief's final review — and was sent for a person's
approval, but nobody decided in time. You decide instead: approve (it is published at once) or
reject (it is turned down, its story dropped, and all the desk's work on it is lost).

Approving is the rule: the fact-check passed and two editors accepted it. Reject only for one of:
1. The advisory law (Taiwan's securities investment advisory law): the article gives the
   company's own buy/sell advice, target prices or forecasts. Reporting facts and what others
   said is fine.
2. A clear error you can name: a headline the body does not support, a contradiction, a number
   or claim with no source behind it.
3. Stale past its hard limit: the context says how old the story was when the desk asked for
   approval, against its section's shelf life. Within the hard limit, timeliness is not a reason
   to reject — the article gives its dates, so a report a few days later is still accurate. A
   piece about one day's price move or price level is the exception: more than 3 days old, reject.
If you are unsure, approve. Do not edit the article.

Read the draft (read_draft); list_claims and read_evidence if you need to see what it stands on.
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
    policies = await get_policies(session, ctx.company_id)
    if story is not None:
        section = await section_of(session, article.id)
        lines += freshness(
            asked=approval.created_at - story.created_at,
            section=section,
            shelf_life=shelf_life_hours(policies, section),
        )
    if no_advice(policies):
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


def freshness(*, asked: timedelta, section: str | None, shelf_life: int) -> list[str]:
    """What the CEO is told of an article's age (D-252): from its story being found to the desk
    asking for approval, against its section's shelf life and hard limit."""
    hours = max(0, round(asked.total_seconds() / 3600))
    limit = shelf_life * HARD_LIMIT_FACTOR
    lines = [
        f"Section: {section or 'none'}; shelf life {shelf_life} hours, hard limit {limit} hours.",
        f"The story was {hours} hours old when the desk asked for approval.",
    ]
    if hours <= shelf_life:
        lines.append("Within its shelf life: timeliness is not a reason to reject.")
    elif hours <= limit:
        lines.append(
            "Past its shelf life but within the hard limit: timeliness is not a reason to reject"
            " (the article gives its dates)."
        )
    else:
        lines.append("Past its hard limit: stale — reject it as such.")
    return lines


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
