"""AD-07: one thing's history beside it — its state changes, what people did to it in the back
office, and for an article the approvals that asked about it — newest first, each with who in
words."""

import uuid
from datetime import UTC, datetime, timedelta

from autora.db.models import Approval, StateTransition
from tests.conftest import unique_company

ACTIVITY = "/api/admin/activity"


async def test_an_articles_history_merges_its_states_its_approvals_and_what_people_did(
    api, db_session, newsroom_room
):
    room = newsroom_room
    article_id = await room.publish()
    await api.post(f"/api/articles/{article_id}/access", json={"access": "members"})
    # an approval that asked about this article, decided by the operator
    asked_at = datetime.now(UTC) - timedelta(hours=1)
    approval = Approval(
        company_id=room.company.id,
        kind="article",
        ref_type="task",
        ref_id=uuid.uuid4(),
        payload={"article_id": article_id},
        summary="核准發布：流明市首座社區微電網啟用",
        requested_by={"kind": "system", "id": "service:newsroom.approve"},
        created_at=asked_at,
    )
    db_session.add(approval)
    await db_session.flush()
    db_session.add(
        StateTransition(
            company_id=room.company.id,
            entity_type="approval",
            entity_id=approval.id,
            from_state="PENDING",
            to_state="APPROVED",
            reason="寫得很好",
            actor={"kind": "human", "id": "operator"},
            at=asked_at + timedelta(minutes=5),
        )
    )
    await db_session.flush()

    entries = (
        await api.get(ACTIVITY, params={"target_type": "article", "target_id": article_id})
    ).json()
    times = [e["at"] for e in entries]
    assert times == sorted(times, reverse=True), "newest first"

    [action] = [e for e in entries if e["kind"] == "action"]
    assert (action["action"], action["status"], action["actor_label"]) == (
        "set_article_access",
        200,
        "操作者權杖",
    )
    assert entries[0] == action, "the person's change is the latest"

    [asked] = [e for e in entries if e["kind"] == "asked"]
    assert (asked["subject"], asked["to_state"], asked["actor_label"]) == (
        "approval",
        "PENDING",
        "系統（service:newsroom.approve）",
    )
    decided = [e for e in entries if e["subject"] == "approval" and e["kind"] == "state"]
    assert [(d["to_state"], d["reason"], d["actor_label"]) for d in decided] == [
        ("APPROVED", "寫得很好", "操作者權杖")
    ]
    own = [e for e in entries if e["subject"] == "article" and e["kind"] == "state"]
    assert own and all(e["subject_id"] == article_id for e in own)


async def test_a_story_and_an_approval_have_theirs(api, db_session):
    company = await unique_company(db_session, "activity")
    story_id = uuid.uuid4()
    db_session.add(
        StateTransition(
            company_id=company.id,
            entity_type="story",
            entity_id=story_id,
            from_state="DISCOVERED",
            to_state="SELECTED",
            reason=None,
            actor={"kind": "human", "id": "operator"},
        )
    )
    await db_session.flush()
    [entry] = (
        await api.get(ACTIVITY, params={"target_type": "story", "target_id": str(story_id)})
    ).json()
    assert (entry["from_state"], entry["to_state"], entry["kind"]) == (
        "DISCOVERED",
        "SELECTED",
        "state",
    )

    nothing = await api.get(
        ACTIVITY, params={"target_type": "approval", "target_id": str(uuid.uuid4())}
    )
    assert nothing.json() == []
    assert (
        await api.get(ACTIVITY, params={"target_type": "agent", "target_id": str(story_id)})
    ).status_code == 422
    assert (
        await api.get(
            ACTIVITY,
            params={"target_type": "story", "target_id": str(story_id)},
            headers={"Authorization": ""},
        )
    ).status_code == 401
