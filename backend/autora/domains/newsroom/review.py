"""The editor's decision on a draft (T-511, platform/05 §3, 3d-office/03 §articles).

The editor reviews the article's current draft once: it runs the fact-check (``run_fact_check``,
layers 1-2), judges the meaning itself (layer 3), then decides with one of these commands. Each
records ARTICLE_REVIEWED (the verdict and whether the fact-check passed):

- ``accept_draft`` (DRAFT -> IN_REVIEW): the draft goes on to approval (a person, or the system
  when the company allows it, D-001). Only with the draft's **latest** fact-check, and only if it
  passed.
- ``request_revision`` (stays DRAFT): the writer gets the editor's issues and
  writes the next version (ARTICLE_REVISION_REQUESTED). A story gets at most ``MAX_REVISIONS``
  revisions; asking for one more rejects the article and drops the story — but only on the
  grounds of ``last_round_basis`` (D-263); anything else is refused and the draft is accepted.

A draft is reviewed once by each reviewer: deciding again on the same draft returns the first
decision when it is the same verdict (a retried call) and refuses a different one.

Then the editor-in-chief's final review (D-110), on the draft the editor accepted (IN_REVIEW),
with ``chief_decide``: ``accept`` (on to a person's approval), ``revise`` (back to DRAFT and the
writer, within the same ``MAX_REVISIONS``) or ``veto`` (the article rejected and the story
dropped; a revision of a published article is dropped instead, the published one stays).
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from autora.db.models import EventRecord
from autora.domains.newsroom.articles import ARTICLE_FSM
from autora.domains.newsroom.events import (
    ArticleRejected,
    ArticleReviewed,
    ArticleRevisionRequested,
)
from autora.domains.newsroom.models import (
    Article,
    ArticleState,
    ArticleVersion,
    FactCheckReport,
    Story,
)
from autora.domains.newsroom.publisher import drop_revision
from autora.domains.newsroom.stories import drop_story
from autora.runtime.actor import Actor
from autora.runtime.events.outbox import emit
from autora.runtime.events.schema import EventPayload, new_event

MAX_REVISIONS = 2
ACCEPT = "accept"
REVISE = "revise"
VETO = "veto"
CHIEF = "editor_in_chief"

# D-263: what can still turn a draft down when no revisions are left — an error a person reading
# it before publication cannot be expected to catch: a wrong fact or number, a claim the evidence
# does not support, a view put in the wrong mouth, a translation that changes the meaning.
# Wording, context and style are not here: cycle 39's only article was dropped in its last round
# over a missing publication date, although the fact-check had passed 8 of 8. The editor's prompt
# already said so (rule 4); this makes it a rule. ``tools.review.IssueKind`` lists them all.
BLOCKING_KINDS = frozenset({"fact", "unsupported", "attribution", "translation"})


class ReviewError(Exception):
    """The draft cannot be decided this way (wrong state, fact-check missing or failed)."""

    retryable = False


def last_round_basis(*, fact_check_passed: bool, issue_kinds: Sequence[str]) -> str | None:
    """Why a draft with no revisions left may be turned down, said for the record: its fact-check
    did not pass, or an issue is of a blocking kind. ``None``: nothing in this review is grounds
    to drop the story, so the draft is accepted (a person still reads it before it runs)."""
    parts = []
    if not fact_check_passed:
        parts.append("the fact-check did not pass")
    major = sorted(set(issue_kinds) & BLOCKING_KINDS)
    if major:
        parts.append("major issues: " + ", ".join(major))
    return "; ".join(parts) or None


def _no_grounds(issue_kinds: Sequence[str], *, instead: str) -> ReviewError:
    return ReviewError(
        "no revisions are left and nothing here is grounds to drop the story: the fact-check "
        f"passed and the issues are only {', '.join(sorted(set(issue_kinds)))} (a story is "
        f"dropped here only for {', '.join(sorted(BLOCKING_KINDS))}). Wording, context and style "
        f"do not drop a story a person still reads before it is published: {instead}. If a claim "
        "is wrong, unsupported, put in the wrong mouth or mistranslated, send it back with that "
        "kind."
    )


@dataclass(frozen=True)
class EventRefs:
    """Who and what the decision's events belong to (the editor's run, when it is one)."""

    agent_id: uuid.UUID | None = None
    run_id: uuid.UUID | None = None
    task_id: uuid.UUID | None = None
    workflow_run_id: uuid.UUID | None = None


NO_REFS = EventRefs()


@dataclass(frozen=True)
class Review:
    article_id: uuid.UUID
    version_id: uuid.UUID
    """The primary-language version of the draft reviewed."""
    verdict: str
    fact_check_passed: bool
    revision: int
    """Revisions asked for so far (this one included)."""
    dropped: bool
    """A revision past the limit: the article was rejected and the story dropped."""
    reused: bool
    """The draft had already been decided this way (nothing happened this time)."""


async def _draft(session: AsyncSession, company_id: uuid.UUID, article_id: uuid.UUID):
    article = await session.get(Article, article_id, with_for_update=True)
    if article is None or article.company_id != company_id:
        raise ReviewError(f"no article {article_id}")
    primary = await session.scalar(
        select(ArticleVersion).where(
            ArticleVersion.draft_group_id == article.current_draft_group_id,
            ArticleVersion.translation_of_version_id.is_(None),
        )
    )
    if primary is None:
        raise ReviewError(f"article {article_id} has no draft to review")
    return article, primary


async def _latest_report(session: AsyncSession, article: Article) -> FactCheckReport | None:
    return await session.scalar(
        select(FactCheckReport)
        .where(
            FactCheckReport.article_id == article.id,
            FactCheckReport.draft_group_id == article.current_draft_group_id,
        )
        .order_by(FactCheckReport.created_at.desc(), FactCheckReport.id.desc())
        .limit(1)
    )


async def _earlier(
    session: AsyncSession,
    article: Article,
    version: ArticleVersion,
    verdict: str,
    *,
    chief: bool = False,
) -> Review | None:
    """The decision this reviewer already took on this draft, if any (a different verdict is
    refused). The editor and the editor-in-chief each review a draft once (D-110)."""
    by_chief = EventRecord.payload["by_role"].astext == CHIEF
    earlier = await session.scalar(
        select(EventRecord).where(
            EventRecord.aggregate_type == "article",
            EventRecord.aggregate_id == article.id,
            EventRecord.event_type == "ARTICLE_REVIEWED",
            EventRecord.payload["version_id"].astext == str(version.id),
            by_chief if chief else ~by_chief,
        )
    )
    if earlier is None:
        return None
    if earlier.payload["verdict"] != verdict:
        raise ReviewError(
            f"this draft (v{version.version}) was already reviewed: {earlier.payload['verdict']}"
        )
    return Review(
        article_id=article.id,
        version_id=version.id,
        verdict=verdict,
        fact_check_passed=earlier.payload["fact_check_passed"],
        revision=article.revision_count,
        dropped=article.state == ArticleState.REJECTED,
        reused=True,
    )


async def _emit(
    session: AsyncSession, article: Article, actor: Actor, refs: EventRefs, payload: EventPayload
) -> None:
    await emit(
        session,
        new_event(
            payload,
            company_id=article.company_id,
            actor=actor,
            aggregate_type="article",
            aggregate_id=article.id,
            agent_id=refs.agent_id,
            run_id=refs.run_id,
            task_id=refs.task_id,
            workflow_run_id=refs.workflow_run_id,
            correlation_id=refs.workflow_run_id,
        ),
    )


async def accept_draft(
    session: AsyncSession,
    *,
    company_id: uuid.UUID,
    article_id: uuid.UUID,
    fact_check_report_id: uuid.UUID,
    actor: Actor,
    by_role: str,
    refs: EventRefs = NO_REFS,
) -> Review:
    article, version = await _draft(session, company_id, article_id)
    earlier = await _earlier(session, article, version, ACCEPT)
    if earlier is not None:
        return earlier
    if article.state != ArticleState.DRAFT:
        raise ReviewError(f"the article is {article.state}: only a draft is accepted")
    latest = await _latest_report(session, article)
    if latest is None:
        raise ReviewError("run the fact-check on this draft first (run_fact_check)")
    if latest.id != fact_check_report_id:
        raise ReviewError(
            f"accept with the draft's latest fact-check ({latest.id}), not {fact_check_report_id}"
        )
    if not latest.passed:
        raise ReviewError("the fact-check did not pass: request a revision instead")
    await ARTICLE_FSM.transition(session, article, ArticleState.IN_REVIEW, actor=actor)
    await _emit(
        session,
        article,
        actor,
        refs,
        ArticleReviewed(
            article_id=article.id,
            version_id=version.id,
            verdict=ACCEPT,
            fact_check_passed=True,
            by_role=by_role,
        ),
    )
    return Review(
        article_id=article.id,
        version_id=version.id,
        verdict=ACCEPT,
        fact_check_passed=True,
        revision=article.revision_count,
        dropped=False,
        reused=False,
    )


async def request_revision(
    session: AsyncSession,
    *,
    company_id: uuid.UUID,
    article_id: uuid.UUID,
    issue_kinds: Sequence[str],
    actor: Actor,
    by_role: str,
    refs: EventRefs = NO_REFS,
    back_to: str = "writer",
) -> Review:
    """``issue_kinds``: the kind of each issue sent back (``tools.review.IssueKind``). With no
    revisions left they decide whether the draft may still be turned down (D-263)."""
    if not issue_kinds:
        raise ReviewError("a revision needs at least one issue")
    article, version = await _draft(session, company_id, article_id)
    earlier = await _earlier(session, article, version, REVISE)
    if earlier is not None:
        return earlier
    if article.state != ArticleState.DRAFT:
        raise ReviewError(f"the article is {article.state}: only a draft is sent back")
    latest = await _latest_report(session, article)
    passed = bool(latest and latest.passed)
    basis = ""
    if article.revision_count >= MAX_REVISIONS:
        basis = last_round_basis(fact_check_passed=passed, issue_kinds=issue_kinds) or ""
        if not basis:
            raise _no_grounds(issue_kinds, instead="accept the draft (accept_draft)")
    await _emit(
        session,
        article,
        actor,
        refs,
        ArticleReviewed(
            article_id=article.id,
            version_id=version.id,
            verdict=REVISE,
            fact_check_passed=passed,
            by_role=by_role,
        ),
    )
    if article.revision_count >= MAX_REVISIONS and article.published_group_id is not None:
        # a revision of a published article (D-045): drop the revision, keep the article
        await drop_revision(
            session,
            article,
            actor=actor,
            reason=f"revision still not ready after {MAX_REVISIONS} rounds ({basis})",
        )
        return Review(
            article_id=article.id,
            version_id=version.id,
            verdict=REVISE,
            fact_check_passed=passed,
            revision=article.revision_count,
            dropped=True,
            reused=False,
        )
    if article.revision_count >= MAX_REVISIONS:
        reason = f"still not ready after {MAX_REVISIONS} revisions ({basis})"
        await ARTICLE_FSM.transition_via(
            session, article, ArticleState.REJECTED, actor=actor, reason=reason
        )
        story = await session.get(Story, article.story_id, with_for_update=True)
        if story is not None:
            await drop_story(session, story, actor=actor, reason=reason)
        await _emit(
            session,
            article,
            actor,
            refs,
            ArticleRejected(
                article_id=article.id,
                by=actor.kind,
                reason=reason,
                issue_kinds=sorted(set(issue_kinds)),
                basis=basis,
            ),
        )
        return Review(
            article_id=article.id,
            version_id=version.id,
            verdict=REVISE,
            fact_check_passed=passed,
            revision=article.revision_count,
            dropped=True,
            reused=False,
        )
    article.revision_count += 1
    await _emit(
        session,
        article,
        actor,
        refs,
        ArticleRevisionRequested(
            article_id=article.id,
            version_id=version.id,
            issues_count=len(issue_kinds),
            by_role=by_role,
            revision=article.revision_count,
            back_to=back_to,
        ),
    )
    return Review(
        article_id=article.id,
        version_id=version.id,
        verdict=REVISE,
        fact_check_passed=passed,
        revision=article.revision_count,
        dropped=False,
        reused=False,
    )


async def _reject(
    session: AsyncSession,
    article: Article,
    actor: Actor,
    refs: EventRefs,
    reason: str,
    *,
    issue_kinds: Sequence[str] = (),
    basis: str = "",
) -> None:
    """Turned down for good: a published article's revision is dropped (the published version
    stays); anything else is rejected and its story dropped."""
    if article.published_group_id is not None:
        await drop_revision(session, article, actor=actor, reason=reason)
        return
    await ARTICLE_FSM.transition_via(
        session, article, ArticleState.REJECTED, actor=actor, reason=reason
    )
    story = await session.get(Story, article.story_id, with_for_update=True)
    if story is not None:
        await drop_story(session, story, actor=actor, reason=reason)
    await _emit(
        session,
        article,
        actor,
        refs,
        ArticleRejected(
            article_id=article.id,
            by=actor.kind,
            reason=reason,
            issue_kinds=sorted(set(issue_kinds)),
            basis=basis,
        ),
    )


async def chief_decide(
    session: AsyncSession,
    *,
    company_id: uuid.UUID,
    article_id: uuid.UUID,
    verdict: str,
    actor: Actor,
    issue_kinds: Sequence[str] = (),
    reason: str | None = None,
    refs: EventRefs = NO_REFS,
) -> Review:
    """The editor-in-chief's final review of the draft the editor accepted (D-110). Like the
    editor's, a revision with none left turns the draft down only on ``last_round_basis`` (D-263);
    a veto is the chief's own way to turn a piece down, and says why."""
    if verdict not in (ACCEPT, REVISE, VETO):
        raise ReviewError(f"the verdict is accept, revise or veto, not {verdict!r}")
    if verdict == REVISE and not issue_kinds:
        raise ReviewError("a revision needs at least one issue")
    if verdict == VETO and not (reason or "").strip():
        raise ReviewError("a veto says why")
    article, version = await _draft(session, company_id, article_id)
    earlier = await _earlier(session, article, version, verdict, chief=True)
    if earlier is not None:
        return earlier
    if article.state != ArticleState.IN_REVIEW:
        raise ReviewError(
            f"the article is {article.state}: the final review is of a draft the editor accepted"
        )
    latest = await _latest_report(session, article)
    passed = bool(latest and latest.passed)
    basis = ""
    if verdict == REVISE and article.revision_count >= MAX_REVISIONS:
        basis = last_round_basis(fact_check_passed=passed, issue_kinds=issue_kinds) or ""
        if not basis:
            raise _no_grounds(issue_kinds, instead="accept it, or veto it with a reason")
    await _emit(
        session,
        article,
        actor,
        refs,
        ArticleReviewed(
            article_id=article.id,
            version_id=version.id,
            verdict=verdict,
            fact_check_passed=passed,
            by_role=CHIEF,
        ),
    )

    def decided(*, dropped: bool) -> Review:
        return Review(
            article_id=article.id,
            version_id=version.id,
            verdict=verdict,
            fact_check_passed=passed,
            revision=article.revision_count,
            dropped=dropped,
            reused=False,
        )

    if verdict == ACCEPT:
        return decided(dropped=False)
    if verdict == VETO:
        await _reject(
            session,
            article,
            actor,
            refs,
            f"vetoed by the editor-in-chief: {reason}",
            basis="the editor-in-chief's veto",
        )
        return decided(dropped=True)
    if article.revision_count >= MAX_REVISIONS:
        await _reject(
            session,
            article,
            actor,
            refs,
            f"still not ready after {MAX_REVISIONS} revisions ({basis})",
            issue_kinds=issue_kinds,
            basis=basis,
        )
        return decided(dropped=True)
    await ARTICLE_FSM.transition(
        session, article, ArticleState.DRAFT, actor=actor, reason="sent back at final review"
    )
    article.revision_count += 1
    await _emit(
        session,
        article,
        actor,
        refs,
        ArticleRevisionRequested(
            article_id=article.id,
            version_id=version.id,
            issues_count=len(issue_kinds),
            by_role=CHIEF,
            revision=article.revision_count,
        ),
    )
    return decided(dropped=False)
