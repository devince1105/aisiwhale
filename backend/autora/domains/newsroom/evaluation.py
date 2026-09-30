"""The newsroom's evaluation set (D-134): the same stories, drafted and reviewed again.

Whether a change to the writer's or the editor's brief sends fewer drafts back cannot be read off
production: a day brings different stories, and a bad day for the model looks like a bad brief.
So a fixed set of the newsroom's own stories — their research and analysis done, their claims and
evidence as they were — is replayed through the part of the line that decides what is published:
draft → review → the editor-in-chief's review, with the same loops as ``story_to_article_v2``
(sent back to the writer at most twice, the chief able to send back or stop it).

It runs in its own database, never the company's: the stories and what they stand on are copied
there, and everything the run writes stays there. The analysis is not redone (it would cost as
much as the rest and change the claims under the draft); its recorded output is replayed by a
service step, so the writer is briefed exactly as it was.

``summarize`` reads a finished run back as numbers per story and in total: the first review's
verdict, rounds, what the editor raised, how it ended, what it cost and how long it took.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

from sqlalchemy import Table, func, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from autora.db.base import Base
from autora.db.models import AgentRun, Task, WorkflowRun
from autora.domains.newsroom.workflow import TEMPLATE
from autora.runtime.dag import NodeSpec, WorkflowTemplate
from autora.runtime.services import ServiceContext

EVAL_TEMPLATE_NAME = "newsroom.eval_v1"
REPLAY = "newsroom.eval_replay_analysis"

EVAL_TEMPLATE = WorkflowTemplate(
    name=EVAL_TEMPLATE_NAME,
    nodes=(
        NodeSpec("analysis", "分析（重播）：{title}", "system", service=REPLAY),
        NodeSpec("draft", "撰稿：{title}", "writer", depends_on=("analysis",)),
        NodeSpec("review", "審稿：{title}", "editor", depends_on=("draft",)),
        NodeSpec("chief_review", "總編終審：{title}", "editor_in_chief", depends_on=("review",)),
    ),
    # the production line's own loops and stop, less a person's approval
    loops=tuple(loop for loop in TEMPLATE.loops if loop.check in ("review", "chief_review")),
    halts=TEMPLATE.halts,
)


async def replay_analysis(ctx: ServiceContext) -> None:
    """The analysis step: its recorded output, as the analyst gave it."""
    await ctx.complete(dict(ctx.params.get("analysis") or {}), summary="analysis replayed")


# --- the set --------------------------------------------------------------------------------


@dataclass(frozen=True)
class Case:
    story_id: uuid.UUID
    title: str
    analysis: dict[str, Any]
    outcome: str
    """How the story ended in production (the article's state), for comparison."""


async def pick_cases(session: AsyncSession, company_id: uuid.UUID, limit: int) -> list[Case]:
    """The company's most recent stories that were analysed: each with its latest analysis."""
    rows = (
        await session.execute(
            text(
                """
                select distinct on (w.params->>'story_id')
                       (w.params->>'story_id')::uuid as story_id,
                       s.title, t.output, coalesce(a.state, 'none') as outcome, t.updated_at
                from workflow_runs w
                join tasks t on t.workflow_run_id = w.id
                join stories s on s.id = (w.params->>'story_id')::uuid
                left join articles a on a.story_id = s.id
                where w.company_id = :company and w.template_name = :template
                  and t.name = 'analysis' and t.state = 'SUCCEEDED' and t.output ? 'claim_ids'
                order by w.params->>'story_id', t.updated_at desc
                """
            ),
            {"company": company_id, "template": TEMPLATE.name},
        )
    ).all()
    rows = sorted(rows, key=lambda r: r.updated_at, reverse=True)[:limit]
    return [Case(r.story_id, r.title, dict(r.output), r.outcome) for r in rows]


# the company's standing (whole tables for the company) and each story's material (by story)
STANDING = (
    "companies",
    "company_policies",
    "business_units",
    "projects",
    "departments",
    "roles",
    "agents",
    "agent_activity",
    "budgets",
    "sources",
)


def _table(name: str) -> Table:
    return Base.metadata.tables[name]


async def _rows(conn: AsyncConnection, name: str, where) -> list[dict[str, Any]]:
    table = _table(name)
    return [dict(row._mapping) for row in (await conn.execute(select(table).where(where(table))))]


async def copy_cases(
    source: AsyncConnection, target: AsyncConnection, company_id: uuid.UUID, cases: list[Case]
) -> dict[str, int]:
    """Copy the company's standing and the cases' stories, claims and evidence, ids and all.

    Foreign keys are not checked while copying (``session_replication_role = replica``): the
    claims point at the tasks and runs that made them, which stay behind. Nothing reads them.
    """
    stories = [c.story_id for c in cases]
    copied: dict[str, int] = {}
    plan: list[tuple[str, list[dict[str, Any]]]] = []
    for name in STANDING:
        key = "id" if name == "companies" else "company_id"
        plan.append((name, await _rows(source, name, lambda t, k=key: t.c[k] == company_id)))
    story_items = await _rows(source, "story_items", lambda t: t.c.story_id.in_(stories))
    claims = await _rows(source, "claims", lambda t: t.c.story_id.in_(stories))
    links = await _rows(
        source, "claim_evidence", lambda t: t.c.claim_id.in_([c["id"] for c in claims])
    )
    evidence = await _rows(
        source, "evidence", lambda t: t.c.id.in_([e["evidence_id"] for e in links])
    )
    item_ids = {i["source_item_id"] for i in story_items} | {
        e["source_item_id"] for e in evidence if e.get("source_item_id")
    }
    plan += [
        ("source_items", await _rows(source, "source_items", lambda t: t.c.id.in_(item_ids))),
        ("stories", await _rows(source, "stories", lambda t: t.c.id.in_(stories))),
        ("story_items", story_items),
        ("claims", claims),
        ("evidence", evidence),
        ("claim_evidence", links),
        (
            "evidence_chunks",
            await _rows(
                source,
                "evidence_chunks",
                lambda t: t.c.evidence_id.in_([e["id"] for e in evidence]),
            ),
        ),
    ]
    await target.execute(text("SET session_replication_role = replica"))
    for name, rows in plan:
        if rows:
            await target.execute(insert(_table(name)).on_conflict_do_nothing(), rows)
        copied[name] = len(rows)
    await target.execute(text("SET session_replication_role = DEFAULT"))
    # every agent idle, as at the start of a day (a paused one would take no work)
    await target.execute(
        update(_table("agent_activity"))
        .where(_table("agent_activity").c.company_id == company_id)
        .values(state="IDLE", detail={}, run_id=None, task_id=None)
    )
    # a story is drafted only while open: whatever became of it in production, here it is new
    await target.execute(
        update(_table("stories"))
        .where(_table("stories").c.id.in_(stories))
        .values(state="SELECTED")
    )
    return copied


# --- the results -----------------------------------------------------------------------------


@dataclass
class CaseResult:
    story_id: str
    title: str
    production: str
    first_review: str | None = None
    drafts: int = 0
    reviews: int = 0
    sent_back: int = 0
    chief: str | None = None
    ended: str = "unfinished"
    """accepted (the chief passed it), rejected (dropped or vetoed), failed, or unfinished."""
    issue_kinds: dict[str, int] = field(default_factory=dict)
    cost_usd: float = 0.0
    seconds: float | None = None


def _ended(run: WorkflowRun, chief: dict[str, Any] | None) -> str:
    if chief and chief.get("verdict") == "accept":
        return "accepted"
    if chief and (chief.get("verdict") == "veto" or chief.get("dropped")):
        return "rejected"
    if run.state == "FAILED":
        return "failed"
    if run.state == "CANCELLED":
        return "rejected"  # the editor dropped it after its last revision
    return "unfinished"


async def result_for(session: AsyncSession, run: WorkflowRun, case: Case) -> CaseResult:
    tasks = (
        await session.scalars(
            select(Task).where(Task.workflow_run_id == run.id).order_by(Task.created_at)
        )
    ).all()
    reviews = [t for t in tasks if t.name == "review" and t.state == "SUCCEEDED"]
    chiefs = [t for t in tasks if t.name == "chief_review" and t.state == "SUCCEEDED"]
    out = CaseResult(story_id=str(case.story_id), title=case.title, production=case.outcome)
    out.drafts = sum(1 for t in tasks if t.name == "draft" and t.state == "SUCCEEDED")
    out.reviews = len(reviews)
    out.sent_back = sum(1 for t in reviews if (t.output or {}).get("verdict") == "revise")
    out.first_review = (reviews[0].output or {}).get("verdict") if reviews else None
    for task in reviews + chiefs:
        for issue in (task.output or {}).get("issues") or []:
            kind = str((issue or {}).get("kind") or "other")
            out.issue_kinds[kind] = out.issue_kinds.get(kind, 0) + 1
    last_chief = chiefs[-1].output if chiefs else None
    out.chief = (last_chief or {}).get("verdict")
    out.ended = _ended(run, last_chief)
    cost = await session.scalar(
        select(func.coalesce(func.sum(AgentRun.cost_usd), 0)).where(
            AgentRun.task_id.in_([t.id for t in tasks])
        )
    )
    out.cost_usd = float(cost or 0)
    if run.finished_at is not None:
        out.seconds = (run.finished_at - run.created_at).total_seconds()
    return out


def summarize(results: list[CaseResult]) -> dict[str, Any]:
    """The set's numbers: what share passed the first review, what share ended accepted, rounds,
    cost and time per story, and what the editor raised, most first."""
    n = len(results) or 1
    kinds: dict[str, int] = {}
    for r in results:
        for k, v in r.issue_kinds.items():
            kinds[k] = kinds.get(k, 0) + v
    timed = [r.seconds for r in results if r.seconds is not None]
    return {
        "stories": len(results),
        "first_review_accepted": sum(1 for r in results if r.first_review == "accept") / n,
        "accepted": sum(1 for r in results if r.ended == "accepted") / n,
        "rejected": sum(1 for r in results if r.ended == "rejected") / n,
        "failed_or_unfinished": sum(1 for r in results if r.ended in ("failed", "unfinished")) / n,
        "drafts_per_story": sum(r.drafts for r in results) / n,
        "cost_per_story_usd": sum(r.cost_usd for r in results) / n,
        "seconds_per_story": (sum(timed) / len(timed)) if timed else None,
        "issue_kinds": dict(sorted(kinds.items(), key=lambda kv: -kv[1])),
        "cases": [asdict(r) for r in results],
    }
