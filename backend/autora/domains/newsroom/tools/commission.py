"""``commission_story``: the editor-in-chief puts the desk to work on a story (T-605b).

One call does what a desk head's decision actually is: the story is selected, and the whole
line starts on it — research, analysis, a bilingual draft, review, approval, publication.

The cap on how much of this may happen in a day is not here. It is the company's
(``max_workflows_per_cycle``), applied by the policy engine when the workflow is instantiated,
which is why this tool goes through ``start_story`` rather than creating tasks itself. An
editor-in-chief who commissions a sixth story on a five-story budget is refused by the company,
not by the newsroom — and that refusal comes back as an answer it can act on.

D-256: a commission has a format (``research.FORMATS``), kept in ``stories.seed.format`` for every
desk to read. A story about a tracked company is a research brief unless the chief says news.
``put_to_work`` is the commission itself, shared with the tools that commission a company report
or a strategy study (``tools/research.py``).
"""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import select

from autora.company.verbs import InstantiateWorkflow, workflows_this_cycle
from autora.db.repositories.companies import get_policies
from autora.domains.newsroom import research, topics
from autora.domains.newsroom.models import Story, StoryState
from autora.domains.newsroom.policy import topic_mix
from autora.domains.newsroom.stories import STORY_FSM
from autora.domains.newsroom.workflow import TEMPLATE_NAME, StartWorkflowError, start_story
from autora.runtime.dag import WorkflowEngine
from autora.runtime.policy import PolicyEngine
from autora.runtime.tools import ToolContext, ToolRegistry, ToolResult

TOOL = "commission_story"


class CommissionStoryArgs(BaseModel):
    story_id: uuid.UUID = Field(description="A candidate story from the ones you were shown.")
    angle: str | None = Field(
        default=None,
        max_length=300,
        description="What this story is about, for the researcher. Leave out if it is obvious.",
    )
    format: Literal["research_brief", "news"] | None = Field(
        default=None,
        description=(
            "research_brief: what the news means for the listed companies it reaches (D-256); "
            "news: a plain report. Leave out: a research brief when the story names a tracked "
            "company, news otherwise."
        ),
    )


def register(registry: ToolRegistry, policy: PolicyEngine, workflows: WorkflowEngine) -> None:
    async def commission_story(args: CommissionStoryArgs, ctx: ToolContext) -> ToolResult:
        story = await ctx.session.get(Story, args.story_id)
        if story is None or story.company_id != ctx.company_id:
            return ToolResult(
                output={"ok": False, "reason": f"no story {args.story_id} in this newsroom"},
                summary="that story is not this newsroom's",
            )
        if story.state in (StoryState.IN_PRODUCTION.value, StoryState.PUBLISHED.value):
            return ToolResult(
                output={"ok": False, "reason": f"{story.title!r} is already {story.state}"},
                summary=f"{story.title[:60]} is already {story.state}",
            )
        fmt = args.format or research.default_format(research.tags_of(topics.story_text(story)))
        return await put_to_work(
            ctx, story, policy=policy, workflows=workflows, angle=args.angle, fmt=fmt
        )

    registry.tool(
        TOOL,
        description=(
            "Commission a candidate story: the desk researches it, writes it in both "
            "languages, reviews it, and publishes it after a person approves. The company may "
            "refuse if the day's work is already full — read ok in the result."
        ),
        side_effect="write",
        retryable=False,
    )(commission_story)


async def put_to_work(
    ctx: ToolContext,
    story: Story,
    *,
    policy: PolicyEngine,
    workflows: WorkflowEngine,
    angle: str | None,
    fmt: str,
) -> ToolResult:
    """The commission: within the desk's mix (D-253), the story selected in its format (D-256),
    and the article workflow started on it."""
    if (mix := topic_mix(await get_policies(ctx.session, ctx.company_id))) is not None:
        # D-253: the desk's mix — focus always, another kind only while it has room
        kind = (await topics.buckets(ctx.session, mix, [story]))[story.id]
        if not mix.may_add(await topics.recent_mix(ctx.session, mix, ctx.company_id), kind):
            share = mix.crypto if kind == "crypto" else mix.other
            return ToolResult(
                output={
                    "ok": False,
                    "reason": f"{story.title!r} is {kind}: at most {share:.0%} of what the"
                    " desk commissions may be, and that is used up for the last 30 days."
                    " Commission a focus story (NVIDIA, TSMC, the AI supply chain) instead.",
                },
                summary=f"{story.title[:60]} is {kind}: no room in the mix",
            )
    if story.state != StoryState.SELECTED.value:
        await STORY_FSM.transition(ctx.session, story, StoryState.SELECTED, actor=ctx.actor)
    if angle:
        story.angle = angle
    if fmt != "news" or research.FORMAT in (story.seed or {}):
        story.seed = {**(story.seed or {}), research.FORMAT: fmt}
    await ctx.session.flush()

    project_id = await _project_for(ctx, story)
    if project_id is None:
        return ToolResult(
            output={"ok": False, "reason": "this newsroom has no project to work in"},
            summary="no project to commission into",
        )
    facts = await workflows_this_cycle(
        ctx.session,
        ctx.company_id,
        InstantiateWorkflow(template=TEMPLATE_NAME, project_id=project_id),
    )
    try:
        run = await start_story(
            ctx.session,
            policy=policy,
            workflows=workflows,
            story=story,
            project_id=project_id,
            actor=ctx.actor,
            role="editor_in_chief",
            facts=facts,
        )
    except StartWorkflowError as refused:
        return ToolResult(
            output={"ok": False, "reason": str(refused)},
            summary=f"the company would not start {story.title[:60]}: {refused}",
        )
    if ctx.cycle_id is not None:
        run.cycle_id = ctx.cycle_id
        await ctx.session.flush()
    return ToolResult(
        output={
            "ok": True,
            "story_id": str(story.id),
            "workflow_run_id": str(run.id),
            "title": story.title,
            "format": fmt,
            "next": "the desk starts on it: research, analysis, draft, review, publication",
        },
        summary=f"commissioned {story.title[:60]} ({fmt})",
    )


async def _project_for(ctx: ToolContext, story: Story) -> uuid.UUID | None:
    """The project the newsroom works in: the story's own, or the newsroom's only one."""
    if story.project_id is not None:
        return story.project_id
    from autora.db.models import BusinessUnit, Project, ProjectState

    return await ctx.session.scalar(
        select(Project.id)
        .where(
            Project.company_id == ctx.company_id,
            Project.state == ProjectState.ACTIVE.value,
            Project.business_unit_id.in_(
                select(BusinessUnit.id).where(
                    BusinessUnit.company_id == ctx.company_id,
                    BusinessUnit.key == "ai_media",
                )
            ),
        )
        .order_by(Project.created_at)
        .limit(1)
    )
