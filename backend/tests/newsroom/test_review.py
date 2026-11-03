"""T-511: the editor's decision on a draft — accept_draft and request_revision."""

import uuid
from typing import get_args

import pytest
from sqlalchemy import select

from autora.app import build_policy_engine
from autora.db.models import EventRecord
from autora.domains.newsroom.models import Article, Claim, Story
from autora.domains.newsroom.publisher import approve_article
from autora.domains.newsroom.review import BLOCKING_KINDS, last_round_basis
from autora.domains.newsroom.tools.review import IssueKind
from autora.runtime.actor import Actor

ISSUE = {"message": "第二段請說明是誰統計的。", "kind": "missing_context", "lang": "en"}
# what the last round may drop a story for (D-263)
MAJOR = {"message": "第三段的金額與來源不符。", "kind": "fact", "lang": "zh-TW"}


async def _events(room, event_type):
    async with room.committed() as session:
        return (
            await session.scalars(
                select(EventRecord)
                .where(
                    EventRecord.company_id == room.company.id,
                    EventRecord.event_type == event_type,
                )
                .order_by(EventRecord.id)
            )
        ).all()


async def _article(room) -> Article:
    async with room.committed() as session:
        return await session.scalar(select(Article).where(Article.story_id == room.story.id))


async def _draft_and_check(room, claim_ids=None):
    drafted = await room.call("write_draft", room.draft(claim_ids or list(room.claims.values())))
    assert drafted.ok, drafted.message
    checked = await room.call("run_fact_check", {"article_id": drafted.output["article_id"]})
    assert checked.ok, checked.message
    return drafted.output, checked.output


async def test_accepting_a_checked_draft_sends_it_to_approval(newsroom_room):
    room = newsroom_room
    draft, report = await _draft_and_check(room)
    assert report["passed"]
    accept = {"article_id": draft["article_id"], "fact_check_report_id": report["report_id"]}
    accepted = await room.call("accept_draft", accept)
    assert accepted.ok, accepted.message
    assert accepted.output["verdict"] == "accept" and accepted.output["reused"] is False
    article = await _article(room)
    assert article.state == "IN_REVIEW"
    [reviewed] = await _events(room, "ARTICLE_REVIEWED")
    assert reviewed.payload == {
        "article_id": draft["article_id"],
        "version_id": draft["versions"]["zh-TW"],
        "verdict": "accept",
        "fact_check_passed": True,
        "by_role": "researcher",  # the room's run is a researcher's
    }
    assert reviewed.task_id is not None and reviewed.aggregate_id == article.id

    # a retried call: the same decision, nothing new
    again = await room.call("accept_draft", accept)
    assert again.ok and again.output["reused"] is True
    assert len(await _events(room, "ARTICLE_REVIEWED")) == 1
    # a different decision on the same draft is refused
    revise = await room.call(
        "request_revision", {"article_id": draft["article_id"], "issues": [ISSUE]}
    )
    assert not revise.ok and "already reviewed: accept" in revise.message

    # the accepted draft goes on to approval
    async with room.committed() as session:
        approved = await approve_article(
            session,
            policy=build_policy_engine(),
            company_id=room.company.id,
            article_id=article.id,
            actor=Actor.human("editor-in-chief"),
        )
        assert approved.state == "APPROVED"
        await session.commit()


async def test_accept_needs_the_latest_passed_fact_check(newsroom_room):
    room = newsroom_room
    drafted = await room.call("write_draft", room.draft(list(room.claims.values())))
    article_id = drafted.output["article_id"]
    no_check = await room.call(
        "accept_draft", {"article_id": article_id, "fact_check_report_id": str(uuid.uuid4())}
    )
    assert not no_check.ok and "run the fact-check on this draft first" in no_check.message

    first = await room.call("run_fact_check", {"article_id": article_id})
    second = await room.call("run_fact_check", {"article_id": article_id})
    stale = await room.call(
        "accept_draft",
        {"article_id": article_id, "fact_check_report_id": first.output["report_id"]},
    )
    assert not stale.ok and f"latest fact-check ({second.output['report_id']})" in stale.message

    # a claim without evidence fails the fact-check: the draft cannot be accepted
    async with room.committed() as session:
        bare = Claim(
            company_id=room.company.id,
            story_id=room.story.id,
            text="It cost NT$999 million.",
            claim_type="number",
        )
        session.add(bare)
        await session.commit()
    _, failed = await _draft_and_check(room, [*room.claims.values(), str(bare.id)])
    assert not failed["passed"]
    refused = await room.call(
        "accept_draft",
        {"article_id": article_id, "fact_check_report_id": failed["report_id"]},
    )
    assert not refused.ok and "did not pass: request a revision" in refused.message
    assert (await _article(room)).state == "DRAFT"


async def test_revisions_are_limited_then_the_story_is_dropped(newsroom_room):
    room = newsroom_room
    for revision in (1, 2):
        draft, _ = await _draft_and_check(room)
        asked = await room.call(
            "request_revision", {"article_id": draft["article_id"], "issues": [ISSUE, ISSUE]}
        )
        assert asked.ok, asked.message
        out = asked.output
        assert out["verdict"] == "revise" and out["revision"] == revision
        assert out["revisions_left"] == 2 - revision and not out["dropped"]
        assert out["issues"][0] == ISSUE
        article = await _article(room)
        assert article.state == "DRAFT" and article.revision_count == revision

    requested = await _events(room, "ARTICLE_REVISION_REQUESTED")
    assert [e.payload["revision"] for e in requested] == [1, 2]
    assert requested[0].payload["issues_count"] == 2
    assert requested[0].payload["by_role"] == "researcher"

    # a third revision for a major error: the article is rejected and the story dropped
    draft, _ = await _draft_and_check(room)
    third = await room.call(
        "request_revision", {"article_id": draft["article_id"], "issues": [MAJOR]}
    )
    assert third.ok, third.message
    assert third.output["dropped"] is True and "story dropped" in third.output["next"]
    article = await _article(room)
    assert article.state == "REJECTED" and article.revision_count == 2
    async with room.committed() as session:
        assert (await session.get(Story, room.story.id)).state == "DROPPED"
    [rejected] = await _events(room, "ARTICLE_REJECTED")
    assert rejected.payload["reason"] == "still not ready after 2 revisions (major issues: fact)"
    assert len(await _events(room, "STORY_DROPPED")) == 1
    assert len(await _events(room, "ARTICLE_REVISION_REQUESTED")) == 2
    # nothing more is written for the story
    late = await room.call("write_draft", room.draft(list(room.claims.values())))
    assert not late.ok and "DROPPED" in late.message


async def test_a_revision_needs_an_issue(newsroom_room):
    room = newsroom_room
    draft, _ = await _draft_and_check(room)
    empty = await room.call("request_revision", {"article_id": draft["article_id"], "issues": []})
    assert not empty.ok and empty.error_class == "InvalidToolArguments"
    other = await room.call(
        "request_revision", {"article_id": str(uuid.uuid4()), "issues": [ISSUE]}
    )
    assert not other.ok and "no article" in other.message


# --- the last round (D-263) -------------------------------------------------------------------
# Cycle 39's only article was dropped in its last round over a date the draft did not state,
# with the fact-check passed 8 of 8. With no revisions left, a story is dropped only for a failed
# fact-check or a major kind of issue; wording, context and style leave the draft to be accepted.


async def _last_round(room, claim_ids=None):
    """A checked draft of an article that has already been revised twice."""
    draft, report = await _draft_and_check(room, claim_ids)
    async with room.committed() as session:
        article = await session.get(Article, uuid.UUID(draft["article_id"]))
        article.revision_count = 2
        await session.commit()
    return draft, report


def test_the_blocking_kinds_are_issue_kinds_and_the_basis_names_them():
    kinds = set(get_args(IssueKind))
    assert BLOCKING_KINDS == {"fact", "unsupported", "attribution", "translation"}
    assert BLOCKING_KINDS <= kinds
    assert kinds - BLOCKING_KINDS == {"missing_context", "style", "other"}

    minor = ["missing_context", "style", "other"]
    assert last_round_basis(fact_check_passed=True, issue_kinds=minor) is None
    assert (
        last_round_basis(fact_check_passed=True, issue_kinds=["translation", "style", "fact"])
        == "major issues: fact, translation"
    )
    assert (
        last_round_basis(fact_check_passed=False, issue_kinds=["style"])
        == "the fact-check did not pass"
    )
    assert (
        last_round_basis(fact_check_passed=False, issue_kinds=["unsupported"])
        == "the fact-check did not pass; major issues: unsupported"
    )


@pytest.mark.parametrize("kind", ["missing_context", "style", "other"])
async def test_the_last_round_does_not_drop_a_story_over_context_or_wording(newsroom_room, kind):
    room = newsroom_room
    draft, report = await _last_round(room)
    assert report["passed"]
    minor = {"message": "第一段請說明資料的發布時間。", "kind": kind}

    refused = await room.call(
        "request_revision", {"article_id": draft["article_id"], "issues": [minor, minor]}
    )

    assert not refused.ok and refused.error_class == "ReviewError"
    assert "no revisions are left and nothing here is grounds to drop the story" in refused.message
    assert "accept_draft" in refused.message
    article = await _article(room)
    assert article.state == "DRAFT" and article.revision_count == 2
    async with room.committed() as session:
        assert (await session.get(Story, room.story.id)).state != "DROPPED"
    for event_type in ("ARTICLE_REJECTED", "STORY_DROPPED", "ARTICLE_REVIEWED"):
        assert await _events(room, event_type) == [], event_type  # a refusal decides nothing

    # the draft is not forced through: it is accepted on its own passed fact-check, and goes on
    # to approval, where a person still reads it
    accepted = await room.call(
        "accept_draft",
        {"article_id": draft["article_id"], "fact_check_report_id": report["report_id"]},
    )
    assert accepted.ok, accepted.message
    assert (await _article(room)).state == "IN_REVIEW"


@pytest.mark.parametrize("kind", sorted(BLOCKING_KINDS))
async def test_the_last_round_still_drops_a_story_for_a_major_error(newsroom_room, kind):
    room = newsroom_room
    draft, report = await _last_round(room)
    assert report["passed"]  # the fact-check alone does not drop it: the editor's reading does
    issues = [
        {"message": "標題措辭可以更精簡。", "kind": "style"},
        {"message": "這段的說法與來源不符。", "kind": kind},
    ]

    dropped = await room.call(
        "request_revision", {"article_id": draft["article_id"], "issues": issues}
    )

    assert dropped.ok, dropped.message
    assert dropped.output["dropped"] is True
    assert (await _article(room)).state == "REJECTED"
    async with room.committed() as session:
        assert (await session.get(Story, room.story.id)).state == "DROPPED"
    reason = f"still not ready after 2 revisions (major issues: {kind})"
    [rejected] = await _events(room, "ARTICLE_REJECTED")
    assert rejected.payload["reason"] == reason
    assert rejected.payload["basis"] == f"major issues: {kind}"
    assert rejected.payload["issue_kinds"] == sorted({"style", kind})  # all raised, not just major
    [story_dropped] = await _events(room, "STORY_DROPPED")
    assert story_dropped.payload["reason"] == reason


async def test_the_last_round_drops_a_draft_whose_fact_check_failed_whatever_the_kind(
    newsroom_room,
):
    """A draft that cannot be accepted is not saved by an issue the editor called style."""
    room = newsroom_room
    async with room.committed() as session:
        bare = Claim(
            company_id=room.company.id,
            story_id=room.story.id,
            text="It cost NT$999 million.",
            claim_type="number",
        )
        session.add(bare)
        await session.commit()
    draft, report = await _last_round(room, [*room.claims.values(), str(bare.id)])
    assert not report["passed"]
    style = {"message": "標題措辭可以更精簡。", "kind": "style"}

    dropped = await room.call(
        "request_revision", {"article_id": draft["article_id"], "issues": [style]}
    )

    assert dropped.ok and dropped.output["dropped"] is True
    [rejected] = await _events(room, "ARTICLE_REJECTED")
    assert rejected.payload["basis"] == "the fact-check did not pass"
    assert rejected.payload["issue_kinds"] == ["style"]
    assert rejected.payload["reason"] == (
        "still not ready after 2 revisions (the fact-check did not pass)"
    )


async def test_a_revision_with_revisions_left_takes_any_kind_of_issue(newsroom_room):
    room = newsroom_room
    draft, _ = await _draft_and_check(room)
    asked = await room.call(
        "request_revision",
        {
            "article_id": draft["article_id"],
            "issues": [{"message": "措辭請再精簡。", "kind": "style"}],
        },
    )
    assert asked.ok and asked.output["dropped"] is False and asked.output["revision"] == 1


async def _chief_last_round(room):
    """An article the editor accepted, revised twice already, at the chief's final review."""
    draft, report = await _draft_and_check(room)
    accepted = await room.call(
        "accept_draft",
        {"article_id": draft["article_id"], "fact_check_report_id": report["report_id"]},
    )
    assert accepted.ok, accepted.message
    async with room.committed() as session:
        article = await session.get(Article, uuid.UUID(draft["article_id"]))
        article.revision_count = 2
        await session.commit()
    return draft["article_id"]


async def test_the_chief_s_last_round_follows_the_same_rule(newsroom_room):
    room = newsroom_room
    article_id = await _chief_last_round(room)
    minor = {"message": "第一段請說明資料的發布時間。", "kind": "missing_context"}

    refused = await room.call(
        "final_review", {"article_id": article_id, "verdict": "revise", "issues": [minor]}
    )

    assert not refused.ok and "nothing here is grounds to drop the story" in refused.message
    assert "veto it with a reason" in refused.message
    assert (await _article(room)).state == "IN_REVIEW"
    assert await _events(room, "ARTICLE_REJECTED") == []

    attribution = {"message": "這句話不是董事長說的。", "kind": "attribution"}
    dropped = await room.call(
        "final_review",
        {"article_id": article_id, "verdict": "revise", "issues": [minor, attribution]},
    )
    assert dropped.ok and dropped.output["dropped"] is True
    [rejected] = await _events(room, "ARTICLE_REJECTED")
    assert rejected.payload["reason"] == (
        "still not ready after 2 revisions (major issues: attribution)"
    )
    assert rejected.payload["issue_kinds"] == ["attribution", "missing_context"]


async def test_the_chief_s_veto_is_recorded_as_one(newsroom_room):
    room = newsroom_room
    article_id = await _chief_last_round(room)

    vetoed = await room.call(
        "final_review",
        {"article_id": article_id, "verdict": "veto", "reason": "這個題材不值得報導。"},
    )

    assert vetoed.ok and vetoed.output["dropped"] is True
    [rejected] = await _events(room, "ARTICLE_REJECTED")
    assert rejected.payload["basis"] == "the editor-in-chief's veto"
    assert rejected.payload["issue_kinds"] == []
    assert rejected.payload["reason"].startswith("vetoed by the editor-in-chief")
