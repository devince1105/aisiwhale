"""``accept_draft`` and ``request_revision`` (T-511): the editor's decision on a draft, through
the commands in ``review.py``; and ``final_review`` (D-110), the editor-in-chief's.

The editor's issues travel in the review task's output (``EditorReview.issues``) to the writer's
revision task; ``request_revision`` echoes them back so the model sees what it sent.
"""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, Field

from autora.db.models import Agent
from autora.domains.newsroom import review
from autora.domains.newsroom.models import Article, ArticleAccess
from autora.domains.newsroom.review import EventRefs, Review
from autora.runtime.tools import ToolContext, ToolRegistry, ToolResult

IssueKind = Literal["fact", "unsupported", "missing_context", "translation", "style", "other"]


class Issue(BaseModel):
    message: str = Field(min_length=3, max_length=1000, description="What to fix, and why.")
    kind: IssueKind = "other"
    lang: str | None = Field(default=None, max_length=10, description="Omit: every language.")
    block_ref: str | None = Field(
        default=None, max_length=40, description='Which block, e.g. "3" (1-based) or a heading.'
    )


class AcceptDraftArgs(BaseModel):
    article_id: uuid.UUID
    fact_check_report_id: uuid.UUID = Field(
        description="The report_id of your run_fact_check on this draft (it must have passed)."
    )


class RequestRevisionArgs(BaseModel):
    article_id: uuid.UUID
    issues: list[Issue] = Field(min_length=1, max_length=20)
    back_to: Literal["writer", "analyst"] = "writer"
    """Who fixes it (D-110): the writer (how the draft says things) or the analyst (the claims
    themselves: a wrong or missing number, a misread source)."""


async def _role(ctx: ToolContext) -> str:
    if ctx.agent_id is not None:
        agent = await ctx.session.get(Agent, ctx.agent_id)
        if agent is not None:
            return agent.role
    return ctx.actor.kind


def _refs(ctx: ToolContext) -> EventRefs:
    return EventRefs(
        agent_id=ctx.agent_id,
        run_id=ctx.run_id,
        task_id=ctx.task_id,
        workflow_run_id=ctx.workflow_run_id,
    )


def _output(decided: Review) -> dict:
    return {
        "article_id": str(decided.article_id),
        "version_id": str(decided.version_id),
        "verdict": decided.verdict,
        "fact_check_passed": decided.fact_check_passed,
        "revision": decided.revision,
        "revisions_left": max(0, review.MAX_REVISIONS - decided.revision),
        "dropped": decided.dropped,
        "reused": decided.reused,
    }


async def accept_draft(args: AcceptDraftArgs, ctx: ToolContext) -> ToolResult:
    decided = await review.accept_draft(
        ctx.session,
        company_id=ctx.company_id,
        article_id=args.article_id,
        fact_check_report_id=args.fact_check_report_id,
        actor=ctx.actor,
        by_role=await _role(ctx),
        refs=_refs(ctx),
    )
    return ToolResult(
        output=_output(decided) | {"next": "the draft goes on to approval"},
        summary=f"accepted the draft of article {args.article_id}",
    )


async def request_revision(args: RequestRevisionArgs, ctx: ToolContext) -> ToolResult:
    decided = await review.request_revision(
        ctx.session,
        company_id=ctx.company_id,
        article_id=args.article_id,
        issues_count=len(args.issues),
        actor=ctx.actor,
        by_role=await _role(ctx),
        refs=_refs(ctx),
        back_to=args.back_to,
    )
    next_step = (
        "too many revisions: the article was rejected and the story dropped"
        if decided.dropped
        else f"the {args.back_to} revises (revision {decided.revision} of {review.MAX_REVISIONS})"
    )
    return ToolResult(
        output=_output(decided)
        | {
            "issues": [i.model_dump(exclude_none=True) for i in args.issues],
            "back_to": args.back_to,
            "next": next_step,
        },
        summary=f"asked for revision {decided.revision} of article {args.article_id} "
        f"({len(args.issues)} issues)"
        if not decided.dropped
        else f"dropped the story of article {args.article_id} after too many revisions",
    )


class FinalReviewArgs(BaseModel):
    article_id: uuid.UUID
    verdict: Literal["accept", "revise", "veto"]
    issues: list[Issue] = Field(default=[], max_length=20)
    """For revise: what the writer must change, and why."""
    reason: str | None = Field(default=None, max_length=1000)
    """For veto: why the piece must not run."""
    vip: bool = Field(
        default=False,
        description="For accept: true makes it VIP (members read all of it; others its opening).",
    )


async def final_review(args: FinalReviewArgs, ctx: ToolContext) -> ToolResult:
    decided = await review.chief_decide(
        ctx.session,
        company_id=ctx.company_id,
        article_id=args.article_id,
        verdict=args.verdict,
        issues_count=len(args.issues),
        reason=args.reason,
        actor=ctx.actor,
        refs=_refs(ctx),
    )
    vip = None
    kept = False
    if args.verdict == "accept" and not decided.dropped:
        # D-159: the chief says whether it is VIP; an operator can change it in the back office
        article = await ctx.session.get(Article, args.article_id)
        if article is not None and article.company_id == ctx.company_id:
            if article.access == ArticleAccess.COIN.value:
                # D-249: COIN and its price are a person's; the chief leaves them as they are
                kept = True
            else:
                article.access = (ArticleAccess.MEMBERS if args.vip else ArticleAccess.FREE).value
                vip = args.vip
    if decided.dropped:
        next_step = "the article is turned down and its story dropped"
    elif args.verdict == "accept":
        next_step = "the article goes on to a person's approval"
    else:
        next_step = f"the writer revises (revision {decided.revision} of {review.MAX_REVISIONS})"
    return ToolResult(
        output=_output(decided)
        | {"issues": [i.model_dump(exclude_none=True) for i in args.issues], "next": next_step}
        | ({"vip": vip} if vip is not None else {})
        | ({"access": "coin, kept: a person set it"} if kept else {}),
        summary=f"final review of article {args.article_id}: {args.verdict}"
        + (" (VIP)" if vip else ""),
    )


def register(registry: ToolRegistry) -> None:
    registry.tool(
        "accept_draft",
        description=(
            "Accept the article's current draft: it goes on to approval. Needs the draft's "
            "latest fact-check (your run_fact_check), passed, and your own check of the meaning."
        ),
        side_effect="write",
        timeout_s=10.0,
        retryable=True,
    )(accept_draft)
    registry.tool(
        "request_revision",
        description=(
            "Send the current draft back with the issues to fix — to the writer (back_to "
            "'writer', the default: how the draft says things) or to the analyst (back_to "
            "'analyst': a claim itself is wrong or missing) (at most "
            f"{review.MAX_REVISIONS} revisions per article; one more drops the story)."
        ),
        side_effect="write",
        timeout_s=10.0,
        retryable=True,
    )(request_revision)
    registry.tool(
        "final_review",
        description=(
            "The editor-in-chief's final review of a draft the editor accepted: accept (on to a "
            "person's approval; vip=true makes it VIP, for members), revise (back to the "
            "writer with issues; counts against the "
            f"article's {review.MAX_REVISIONS} revisions) or veto (with a reason: the piece is "
            "turned down and its story dropped)."
        ),
        side_effect="write",
        timeout_s=10.0,
        retryable=True,
    )(final_review)
