"""D-109: 團隊群組 — the office's group chat: what happened, as the company recorded it, and the
operator's notes and briefs."""

from autora.db.models import Project
from autora.domains.newsroom.models import Story


async def test_a_note_joins_the_feed_and_the_steps_between_do_not(api, newsroom_room):
    company = newsroom_room.company.id
    posted = await api.post(f"/api/companies/{company}/team/messages", json={"text": "  早安  "})
    assert posted.status_code == 201, posted.text
    assert posted.json()["story_id"] is None

    feed = (await api.get(f"/api/companies/{company}/team/feed")).json()
    last = feed["items"][-1]
    assert (last["event_type"], last["payload"]["text"], last["payload"]["kind"]) == (
        "TEAM_MESSAGE_POSTED",
        "早安",
        "note",
    )
    assert last["actor"]["kind"] == "human"
    # only what a person would want to hear about: no polls, no thinking, no tool calls
    kinds = {e["event_type"] for e in feed["items"]}
    assert not kinds & {"SOURCE_POLLED", "AGENT_THINKING", "TOOL_CALLED", "STORY_DISCOVERED"}

    # older ones a page at a time, oldest first
    for n in range(3):
        await api.post(f"/api/companies/{company}/team/messages", json={"text": f"第 {n} 則"})
    page = (await api.get(f"/api/companies/{company}/team/feed", params={"limit": 2})).json()
    assert [e["payload"]["text"] for e in page["items"]] == ["第 1 則", "第 2 則"]
    assert page["has_more"] is True
    older = await api.get(
        f"/api/companies/{company}/team/feed",
        params={"limit": 1, "before": page["items"][0]["seq"]},
    )
    assert [e["payload"]["text"] for e in older.json()["items"]] == ["第 0 則"]


async def test_a_brief_is_a_story_taken_straight_into_production(api, newsroom_room, db_session):
    room = newsroom_room
    db_session.add(
        Project(company_id=room.company.id, name="newsroom", state="ACTIVE", kill_criteria={})
    )
    await db_session.flush()
    posted = await api.post(
        f"/api/companies/{room.company.id}/team/messages",
        json={"text": "寫一篇 NVDA 財報", "kind": "brief"},
    )
    assert posted.status_code == 201, posted.text
    story = await db_session.get(Story, posted.json()["story_id"])
    await db_session.refresh(story)
    assert story.title == "寫一篇 NVDA 財報" and story.seed == {"query": "寫一篇 NVDA 財報"}
    assert story.state == "IN_PRODUCTION"
    assert posted.json()["workflow_run_id"]

    feed = (await api.get(f"/api/companies/{room.company.id}/team/feed")).json()["items"]
    kinds = [e["event_type"] for e in feed]
    assert "STORY_SELECTED" in kinds and kinds[-1] == "TEAM_MESSAGE_POSTED"
    assert (feed[-1]["payload"]["ref_type"], feed[-1]["payload"]["ref_id"]) == (
        "story",
        str(story.id),
    )


async def test_a_message_needs_words_and_the_operator(api, newsroom_room):
    company = newsroom_room.company.id
    blank = await api.post(f"/api/companies/{company}/team/messages", json={"text": "   "})
    assert blank.status_code == 422
    anonymous = await api.get(f"/api/companies/{company}/team/feed", headers={"Authorization": ""})
    assert anonymous.status_code == 401
