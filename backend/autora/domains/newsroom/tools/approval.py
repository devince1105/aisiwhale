"""``decide_unanswered_article`` (D-157): the CEO's decision on an article nobody approved in time.

An article's approval that no person answered within its 24 hours goes to the CEO
(``ApprovalService.delegate_when_unanswered``). This is how she decides it: approve or reject, with
a reason, through ``ApprovalService.decide_delegated`` — the same path a person's decision takes,
recorded as her. A person may still decide while she reads; if one did, the tool says so instead
of failing, and there is nothing left for her to do.
"""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, Field

from autora.db.models import Approval
from autora.runtime.approvals import ApprovalService
from autora.runtime.approvals.service import ApprovalError
from autora.runtime.tools import ToolContext, ToolRegistry, ToolResult


class DecideUnansweredArgs(BaseModel):
    approval_id: uuid.UUID
    decision: Literal["approve", "reject"]
    reason: str = Field(
        min_length=5, max_length=500, description="Why, in one or two sentences (zh-TW)."
    )


def decide_unanswered_article(approvals: ApprovalService):
    async def decide(args: DecideUnansweredArgs, ctx: ToolContext) -> ToolResult:
        approval = await ctx.session.get(Approval, args.approval_id)
        if approval is None or approval.company_id != ctx.company_id:
            raise ApprovalError(f"approval {args.approval_id} not found")
        if approval.state != "PENDING":
            # a person got there first: nothing to decide
            return ToolResult(
                output={"already_decided": approval.state, "by": approval.decided_by},
                summary=f"already {approval.state}: nothing to decide",
            )
        if ctx.task_id is None:
            raise ApprovalError("a delegated decision is made from its task")
        decided = await approvals.decide_delegated(
            ctx.session,
            approval.id,
            outcome=args.decision,
            actor=ctx.actor,
            reason=args.reason,
            task_id=ctx.task_id,
        )
        return ToolResult(
            output={"approval_id": str(decided.id), "state": decided.state, "reason": args.reason},
            summary=f"{args.decision}: {args.reason}"[:200],
        )

    return decide


def register(registry: ToolRegistry, approvals: ApprovalService) -> None:
    registry.tool(
        "decide_unanswered_article",
        description=(
            "Decide an article's approval that no person answered in 24 hours: approve "
            "(it is published) or reject (it is turned down and its story dropped), with a reason. "
            "Only for the approval your task was given."
        ),
        side_effect="write",
        timeout_s=15.0,
        retryable=False,
    )(decide_unanswered_article(approvals))
