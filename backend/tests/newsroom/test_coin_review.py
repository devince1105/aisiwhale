"""P4 (D-249): the editor-in-chief's final review leaves a COIN article as a person set it.

VIP or free is the chief's to say (D-159); COIN and its price are only ever a person's, in the
back office — so an accept, VIP or not, changes neither, and the report is not held to a VIP
answer it could not have given.
"""

import uuid
from types import SimpleNamespace

from sqlalchemy import select

from autora.db.models import EventRecord
from autora.domains.newsroom.agents.chief_review import ChiefReview, decided_here
from autora.domains.newsroom.models import Article, ArticleAccess


async def _in_review(room) -> uuid.UUID:
    drafted = await room.call("write_draft", room.draft(list(room.claims.values())))
    article_id = drafted.output["article_id"]
    report = await room.call("run_fact_check", {"article_id": article_id})
    accepted = await room.call(
        "accept_draft",
        {"article_id": article_id, "fact_check_report_id": report.output["report_id"]},
    )
    assert accepted.ok, accepted.message
    return uuid.UUID(article_id)


async def _set(room, article_id, access: ArticleAccess, price: int | None) -> None:
    async with room.committed() as session:
        row = await session.get(Article, article_id)
        row.access, row.coin_price = access.value, price
        await session.commit()


async def _report_checks(room, article_id, *, vip: bool) -> list[str]:
    async with room.committed() as session:
        task_id = await session.scalar(
            select(EventRecord.task_id)
            .where(EventRecord.event_type == "ARTICLE_REVIEWED")
            .where(EventRecord.payload["by_role"].astext == "editor_in_chief")
            .where(EventRecord.payload["article_id"].astext == str(article_id))
        )
        ctx = SimpleNamespace(
            company_id=room.company.id, task=SimpleNamespace(id=task_id, input={})
        )
        note = ChiefReview(article_id=article_id, verdict="accept", vip=vip)
        return await decided_here(session, ctx, note)


async def test_accepting_a_coin_article_keeps_it_coin_at_its_price(newsroom_room):
    room = newsroom_room
    article_id = await _in_review(room)
    await _set(room, article_id, ArticleAccess.COIN, 7)

    done = await room.call(
        "final_review", {"article_id": str(article_id), "verdict": "accept", "vip": True}
    )

    assert done.ok, done.message
    assert "vip" not in done.output
    assert done.output["access"] == "coin, kept: a person set it"
    async with room.committed() as session:
        row = await session.get(Article, article_id)
        assert (row.access, row.coin_price) == ("coin", 7)
    for vip in (True, False):
        assert await _report_checks(room, article_id, vip=vip) == []


async def test_any_other_article_is_still_the_chief_s_to_make_vip(newsroom_room):
    room = newsroom_room
    article_id = await _in_review(room)

    done = await room.call(
        "final_review", {"article_id": str(article_id), "verdict": "accept", "vip": True}
    )

    assert done.ok, done.message
    assert done.output["vip"] is True and "access" not in done.output
    async with room.committed() as session:
        assert (await session.get(Article, article_id)).access == "members"
    assert await _report_checks(room, article_id, vip=True) == []
    assert await _report_checks(room, article_id, vip=False) == [
        "vip is true: report what you set with final_review"
    ]
