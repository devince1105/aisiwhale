"""The newsroom's workflow: one story to one published article (T-514, platform/05 §2,
3d-office/06 §1).

    research -> analysis -> draft -> review -> approve -> publish -> distribute
                              ^         |
                              +-revise--+   (at most two revisions)

- The five agent steps are the newsroom agents (T-506 .. T-513).
- ``review`` is a loop check: when the editor asks for a revision, the engine adds another
  ``draft`` (with the editor's issues in ``params.issues``) and ``review``, and ``approve`` waits
  for the new review. A third request for a revision has already rejected the article and dropped
  the story (``review.py``); the engine then cancels what was waiting.
- ``approve`` is a service step (role ``human``): the system approves the article itself when the
  company allows it after a passed fact-check (D-001, off by default); otherwise a person decides
  through an approval (``approve_article``), whose decision approves or rejects the article in the
  same transaction (``on_article_decided``).
- ``publish`` is a service step (role ``system``): the publisher (T-512).
- The measurement schedule after publication (+1h, +24h, +7d) arrives with analytics (T-516).

``start_story`` starts the workflow for a selected story (the story goes IN_PRODUCTION).

**Revising a published article** (D-045) is its own, shorter template — draft, review, approve,
publish: the story's evidence and claims are already there, and the person's reason is the
writer's first issue. ``start_article_revision`` starts it; the site keeps the published version
until the new one is published.
Starting the template some other way (the generic API) needs ``story_id`` and ``title`` params.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from autora.company.agents import hire_agent
from autora.company.organization import role_by_key
from autora.company.workflows import StartWorkflowError, start_workflow
from autora.db.models import Agent, AgentStatus, Approval, Task, WorkflowRun
from autora.db.repositories.companies import get_policies
from autora.domains.newsroom import organization, personas
from autora.domains.newsroom.models import Article, ArticleState, Story, StoryState
from autora.domains.newsroom.policy import ceo_decides_when_unanswered
from autora.domains.newsroom.publisher import (
    NotAllowed,
    PublishError,
    approve_article,
    publish_article,
    reject_article,
    return_article,
    start_revision,
)
from autora.domains.newsroom.stories import STORY_FSM
from autora.runtime.actor import Actor
from autora.runtime.approvals import ApprovalError
from autora.runtime.dag import (
    Halt,
    Loop,
    NodeSpec,
    TemplateRegistry,
    WorkflowEngine,
    WorkflowTemplate,
)
from autora.runtime.policy import PolicyEngine
from autora.runtime.services import ServiceContext

TEMPLATE_NAME = "newsroom.story_to_article_v2"
APPROVE = "newsroom.approve"
PUBLISH = "newsroom.publish"
APPROVE_ACTION = "approve_article"
ARTICLE_APPROVAL = "article"
"""What the newsroom asks people to decide about. The word is the newsroom's, not the
runtime's: the runtime stores the token and does not know what an article is (§9)."""
MAX_REVISIONS = 2  # review.MAX_REVISIONS: the editor's tool drops the story after that


def _revise(output: dict[str, Any]) -> bool:
    return output.get("verdict") == "revise"


def _to_analyst(output: dict[str, Any]) -> bool:
    """The editor found the problem in the claims themselves (D-110): the analysis is redone."""
    return _revise(output) and output.get("back_to") == "analyst"


def _to_writer(output: dict[str, Any]) -> bool:
    return _revise(output) and output.get("back_to") != "analyst"


def _chief_stops(output: dict[str, Any]) -> bool:
    """The editor-in-chief vetoed the piece, or sent it back once too often and the story was
    dropped (D-110): nothing downstream runs."""
    return output.get("verdict") == "veto" or bool(output.get("dropped"))


def _issues(output: dict[str, Any]) -> dict[str, Any]:
    return {"issues": output.get("issues") or []}


def _sent_back(output: dict[str, Any]) -> bool:
    """The approval step's output when a person sent the article back (D-044)."""
    return output.get("decision") == "revise"


def _their_reason(output: dict[str, Any]) -> dict[str, Any]:
    """What the writer is told: the person's reason, as one issue like the editor's."""
    return {"issues": [{"message": f"審批退回（人工）：{output.get('reason') or ''}"}]}


CHIEF_LOOP = Loop(
    check="chief_review",
    back_to="draft",
    again=_revise,
    carry=_issues,
    max_rounds=MAX_REVISIONS,
    round_label="{name}（總編退回第 {round} 輪）",
)
"""The editor-in-chief sends a draft back: the writer revises, the editor reviews it again, and it
comes back to the chief (D-110)."""
CHIEF_HALT = Halt("chief_review", when=_chief_stops, reason="the editor-in-chief stopped it")


TEMPLATE = WorkflowTemplate(
    name=TEMPLATE_NAME,
    nodes=(
        NodeSpec("research", "研究：{title}", "researcher"),
        NodeSpec("analysis", "分析：{title}", "analyst", depends_on=("research",)),
        NodeSpec("draft", "撰稿：{title}", "writer", depends_on=("analysis",)),
        NodeSpec("review", "審稿：{title}", "editor", depends_on=("draft",)),
        # the editor-in-chief's final review, before a person approves (D-110)
        NodeSpec("chief_review", "總編終審：{title}", "editor_in_chief", depends_on=("review",)),
        # marketing finds the cover alongside the draft, so the approval shows it; outside every
        # loop (nothing between draft and approve depends on it), so a send-back does not
        # search again (D-142)
        NodeSpec("cover", "找首圖：{title}", "marketing", depends_on=("analysis",)),
        NodeSpec(
            "approve",
            "核准：{title}",
            "human",
            depends_on=("chief_review", "cover"),
            service=APPROVE,
        ),
        NodeSpec("publish", "發布：{title}", "system", depends_on=("approve",), service=PUBLISH),
        NodeSpec("distribute", "推廣：{title}", "marketing", depends_on=("publish",)),
    ),
    loops=(
        # the editor sends it back to the analyst (the claims) or the writer (the draft); both
        # count against the same revisions (D-110)
        Loop(
            check="review",
            back_to="analysis",
            again=_to_analyst,
            carry=_issues,
            max_rounds=MAX_REVISIONS,
            round_label="{name}（第 {round} 輪）",
        ),
        Loop(
            check="review",
            back_to="draft",
            again=_to_writer,
            carry=_issues,
            max_rounds=MAX_REVISIONS,
            round_label="{name}（第 {round} 輪）",
        ),
        CHIEF_LOOP,
        # D-044: a person sends it back from approval; the writer drafts again with their reason,
        # the editor reviews again, and it comes back to approval. The editor and the chief have
        # their rounds again from there (D-233): counted from the start, a draft that had used
        # them was dropped at the editor's first objection, and never came back to the person.
        Loop(
            check="approve",
            back_to="draft",
            again=_sent_back,
            carry=_their_reason,
            max_rounds=MAX_REVISIONS,
            round_label="{name}（退回後第 {round} 輪）",
            restarts=("review", "chief_review"),
        ),
    ),
    halts=(CHIEF_HALT,),
)


REVISION_TEMPLATE_NAME = "newsroom.article_revision_v1"

REVISION_TEMPLATE = WorkflowTemplate(
    name=REVISION_TEMPLATE_NAME,
    nodes=(
        NodeSpec("draft", "修改：{title}", "writer"),
        NodeSpec("review", "審稿（修改）：{title}", "editor", depends_on=("draft",)),
        NodeSpec(
            "chief_review", "總編終審（修改）：{title}", "editor_in_chief", depends_on=("review",)
        ),
        NodeSpec(
            "approve",
            "核准（修改）：{title}",
            "human",
            depends_on=("chief_review",),
            service=APPROVE,
        ),
        NodeSpec(
            "publish", "發布（修改）：{title}", "system", depends_on=("approve",), service=PUBLISH
        ),
    ),
    # no analysis here: whatever the editor sends back, the writer revises
    loops=(
        Loop(
            check="review",
            back_to="draft",
            again=_revise,
            carry=_issues,
            max_rounds=MAX_REVISIONS,
            round_label="{name}（第 {round} 輪）",
        ),
        CHIEF_LOOP,
        *(loop for loop in TEMPLATE.loops if loop.check == "approve"),
    ),
    halts=(CHIEF_HALT,),
)
"""D-045: a published article changed. The same rounds as a story's — the editor's, the
editor-in-chief's and a person's sending back — except that there is no analysis to go back to."""


UNANSWERED_TEMPLATE_NAME = "newsroom.unanswered_approval_v1"
UNANSWERED_TASK = "decide_unanswered"

UNANSWERED_TEMPLATE = WorkflowTemplate(
    name=UNANSWERED_TEMPLATE_NAME,
    nodes=(NodeSpec(UNANSWERED_TASK, "代為終審：{title}", "ceo", max_attempts=2),),
)
"""D-157: the CEO decides an article nobody approved in 24 hours."""


def register_templates(templates: TemplateRegistry) -> None:
    templates.register(TEMPLATE)
    templates.register(REVISION_TEMPLATE)
    templates.register(UNANSWERED_TEMPLATE)


# --- staffing ---------------------------------------------------------------------------------

DISPLAY_NAMES = {role: persona.name for role, persona in personas.STAFF.items()}
"""The newsroom's desks and who sits at each (D-110: ``personas.py``). The editor-in-chief heads
it: she decides what the desk covers, and nobody else does (T-605b)."""


async def staff_newsroom(
    session: AsyncSession, company_id: uuid.UUID, *, actor: Actor
) -> list[Agent]:
    """Build the newsroom's place in the company, then hire one agent into each position.

    The organisation comes first (T-600): an agent is hired *into a role*, so it arrives with a
    department and the position's defaults rather than with a bare role string. The
    editor-in-chief's chair is left empty on purpose — its agent is T-605b.
    """
    await organization.build(session, company_id, actor=actor)
    existing = set(
        (
            await session.scalars(
                select(Agent.role).where(
                    Agent.company_id == company_id, Agent.status == AgentStatus.ACTIVE
                )
            )
        ).all()
    )
    hired = []
    for role, persona in personas.STAFF.items():
        if role in existing:
            continue
        position = await role_by_key(session, company_id, role)
        hired.append(
            await hire_agent(
                session,
                company_id=company_id,
                role=role,
                display_name=persona.name,
                description=persona.description,
                avatar_key=persona.avatar,
                actor=actor,
                position=position,
            )
        )
    return hired


async def start_story(
    session: AsyncSession,
    *,
    policy: PolicyEngine,
    workflows: WorkflowEngine,
    story: Story,
    project_id: uuid.UUID,
    actor: Actor,
    role: str | None = None,
    facts: dict[str, Any] | None = None,
    demo: dict[str, Any] | None = None,
) -> WorkflowRun:
    """Start the workflow for a SELECTED story (the ``instantiate_workflow`` command: the policy
    decides and the decision is recorded); the story goes IN_PRODUCTION. ``demo``: knobs for the
    simulated model only (``simulation.py``: pace, a revision on the first review)."""
    if story.state != StoryState.SELECTED:
        raise StartWorkflowError(f"the story is {story.state}; only a selected story is started")
    run, _ = await start_workflow(
        session,
        policy=policy,
        workflows=workflows,
        company_id=story.company_id,
        project_id=project_id,
        template=TEMPLATE_NAME,
        params={"story_id": str(story.id), "title": story.title[:80]}
        | ({"demo": demo} if demo else {}),
        actor=actor,
        role=role,
        facts=facts,
    )
    await STORY_FSM.transition(session, story, StoryState.IN_PRODUCTION, actor=actor)
    return run


async def start_article_revision(
    session: AsyncSession,
    *,
    policy: PolicyEngine,
    workflows: WorkflowEngine,
    company_id: uuid.UUID,
    article_id: uuid.UUID,
    actor: Actor,
    reason: str,
) -> WorkflowRun:
    """A person asks for a published article to be changed (D-045): the article is a draft
    again and a revision workflow starts, in the project its story was made in."""
    article = await start_revision(
        session, company_id=company_id, article_id=article_id, actor=actor, reason=reason
    )
    story = await session.get(Story, article.story_id)
    assert story is not None
    project_id = await session.scalar(
        select(WorkflowRun.project_id)
        .where(
            WorkflowRun.company_id == company_id,
            WorkflowRun.params["story_id"].astext == str(story.id),
        )
        .order_by(WorkflowRun.id.desc())
        .limit(1)
    )
    if project_id is None:
        raise StartWorkflowError(f"no project made story {story.id}; start the revision by hand")
    run, _ = await start_workflow(
        session,
        policy=policy,
        workflows=workflows,
        company_id=company_id,
        project_id=project_id,
        template=REVISION_TEMPLATE_NAME,
        params={
            "story_id": str(story.id),
            "article_id": str(article.id),
            "title": story.title[:80],
            "issues": [{"message": f"發布後修改（人工）：{reason}"}],
        },
        actor=actor,
    )
    return run


async def _story_article(ctx: ServiceContext) -> Article | None:
    story_id = ctx.params.get("story_id")
    if not story_id:
        return None
    return await ctx.session.scalar(
        select(Article).where(
            Article.story_id == uuid.UUID(str(story_id)),
            Article.company_id == ctx.task.company_id,
        )
    )


async def returns_left(session: AsyncSession, approve: Task) -> int:
    """How many more times a person may send the article back from this approval: the run's
    loop on ``approve`` has ``MAX_REVISIONS`` rounds (D-044). The card offers 退回修改 only
    while there is one (D-233)."""
    if approve.workflow_run_id is None:
        return 0
    approvals = await session.scalar(
        select(func.count()).where(
            Task.workflow_run_id == approve.workflow_run_id, Task.name == approve.name
        )
    )
    return max(0, MAX_REVISIONS - ((approvals or 1) - 1))


# --- service steps ----------------------------------------------------------------------------


async def approve_step(ctx: ServiceContext) -> None:
    article = await _story_article(ctx)
    if article is None:
        await ctx.fail("NoArticle", "the story has no article to approve")
        return
    if article.state in (ArticleState.APPROVED, ArticleState.PUBLISHED):
        await ctx.complete({"article_id": str(article.id), "approved_by": "earlier"})
        return
    if article.state != ArticleState.IN_REVIEW:
        await ctx.fail("NotInReview", f"the article is {article.state}, not accepted by the editor")
        return
    try:
        await approve_article(
            ctx.session,
            policy=ctx.policy,
            company_id=article.company_id,
            article_id=article.id,
            actor=ctx.actor,
            reason="automatic approval after a passed fact-check",
        )
    except NotAllowed as refused:
        if refused.outcome != "needs_approval":
            await ctx.fail("NotAllowed", refused.reason)
            return
        await ctx.request_approval(
            kind=ARTICLE_APPROVAL,
            action=APPROVE_ACTION,
            summary=f"申請發布：{article.title}"[:300],
            payload={
                "article_id": str(article.id),
                "story_id": str(article.story_id),
                "draft_group_id": str(article.current_draft_group_id),
                "returns_left": await returns_left(ctx.session, ctx.task),
            },
        )
        return
    except PublishError as error:
        await ctx.fail("PublishError", str(error))
        return
    await ctx.complete(
        {"article_id": str(article.id), "approved_by": "system"},
        summary="approved automatically (fact-check passed)",
    )


async def publish_step(ctx: ServiceContext) -> None:
    article = await _story_article(ctx)
    if article is None:
        await ctx.fail("NoArticle", "the story has no article to publish")
        return
    try:
        published = await publish_article(
            ctx.session,
            policy=ctx.policy,
            company_id=article.company_id,
            article_id=article.id,
            actor=ctx.actor,
        )
    except (PublishError, NotAllowed) as error:
        await ctx.fail(type(error).__name__, str(error))
        return
    await ctx.complete(
        {
            "article_id": str(published.article_id),
            "slug": published.slug,
            "langs": published.langs,
            "urls": published.urls,
            "distribution_id": str(published.distribution_id),
        },
        summary=f"published {published.urls.get(published.langs[0], published.slug)}",
    )


def on_article_decided(policy: PolicyEngine):
    """A person's decision on an ``approve_article`` approval approves, sends back (D-044) or
    rejects the article. An agent's is the CEO's, on an approval nobody answered (D-157)."""

    async def hook(
        session: AsyncSession, approval: Approval, outcome: str, actor: Actor, reason: str | None
    ) -> None:
        article_id = uuid.UUID(approval.payload["article_id"])
        if outcome == "approve":
            await approve_article(
                session,
                policy=policy,
                company_id=approval.company_id,
                article_id=article_id,
                actor=actor,
                reason=reason,
                delegated=actor.kind == "agent",
            )
        elif outcome == "revise":
            waiting = await session.get(Task, approval.task_id) if approval.task_id else None
            if waiting is None or await returns_left(session, waiting) < 1:
                # a third would cancel the run and leave the article a draft nobody writes
                raise ApprovalError(
                    f"sent back {MAX_REVISIONS} times already: approve it or reject it"
                )
            await return_article(
                session,
                company_id=approval.company_id,
                article_id=article_id,
                actor=actor,
                reason=reason or "",
            )
        else:
            await reject_article(
                session,
                company_id=approval.company_id,
                article_id=article_id,
                actor=actor,
                reason=reason or "rejected at approval",
                delegated=actor.kind == "agent",
            )

    return hook


def delegate_article_to_ceo(workflows: WorkflowEngine):
    """D-157: an article's approval nobody answered goes to the CEO — a one-task workflow in the
    article's own project, so its cost is the newsroom's. None (a person is asked again) when the
    company turned this off or has no CEO at work."""

    async def delegate(session: AsyncSession, approval: Approval) -> uuid.UUID | None:
        if not ceo_decides_when_unanswered(await get_policies(session, approval.company_id)):
            return None
        ceo = await session.scalar(
            select(Agent.id).where(
                Agent.company_id == approval.company_id,
                Agent.role == "ceo",
                Agent.status == AgentStatus.ACTIVE.value,
            )
        )
        waiting = await session.get(Task, approval.task_id) if approval.task_id else None
        if ceo is None or waiting is None:
            return None
        article = await session.get(Article, uuid.UUID(approval.payload["article_id"]))
        if article is None:
            return None
        origin = (
            await session.get(WorkflowRun, waiting.workflow_run_id)
            if waiting.workflow_run_id
            else None
        )
        demo = (origin.params or {}).get("demo") if origin is not None else None
        _, tasks = await workflows.instantiate(
            session,
            UNANSWERED_TEMPLATE_NAME,
            company_id=approval.company_id,
            project_id=waiting.project_id,
            params={
                "approval_id": str(approval.id),
                "article_id": str(article.id),
                "story_id": str(article.story_id),
                "title": article.title[:80],
            }
            | ({"demo": demo} if demo else {}),
        )
        return tasks[UNANSWERED_TASK].id

    return delegate
