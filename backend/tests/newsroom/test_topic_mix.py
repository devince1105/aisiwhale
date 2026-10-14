"""D-253: the desk covers NVIDIA, TSMC and the AI supply chain — nine in ten — and crypto one in a
hundred: which candidates the editor-in-chief is shown, and which commissions are refused.

Without the company policy ``newsroom.topic_mix`` nothing changes (``test_editor_in_chief``).
"""

import uuid
from collections import Counter
from decimal import Decimal

from sqlalchemy import select

from autora.app import build_runtime
from autora.db.models import WorkflowRun
from autora.db.repositories.companies import upsert_policy
from autora.domains.newsroom.agents.editor_in_chief import CANDIDATES, choose, desk_context
from autora.domains.newsroom.models import Story, StoryState
from autora.domains.newsroom.policy import (
    DEFAULT_FOCUS_TERMS,
    TOPIC_MIX_KEY,
    TopicMix,
    topic_mix,
)
from autora.domains.newsroom.tools.commission import register as register_commission
from autora.domains.newsroom.workflow import TEMPLATE_NAME
from autora.runtime.actor import Actor
from autora.runtime.tools import ToolRegistry
from tests.newsroom.test_editor_in_chief import HUMAN, _ctx, _desk

MIX = TopicMix(DEFAULT_FOCUS_TERMS, crypto=0.01, other=0.09)


def test_a_story_s_kind():
    assert MIX.bucket(section="tw", text="台積電 9 月營收創新高") == "focus"
    assert MIX.bucket(section="us", text="Nvidia unveils a new GPU") == "focus"
    assert MIX.bucket(section="ai", text="SK hynix ships HBM4") == "focus"
    assert MIX.bucket(section="crypto", text="比特幣 ETF，輝達也受影響") == "crypto"
    assert MIX.bucket(section="tw", text="富邦金取得市政大樓地上權") == "other"
    assert MIX.bucket(section=None, text="創意十足的行銷") == "other", "創意 alone is not 創意電子"


def test_room_in_the_mix():
    assert MIX.may_add(Counter(), "focus")
    assert not MIX.may_add(Counter(), "crypto"), "the first story of a month is never crypto"
    assert not MIX.may_add(Counter(focus=8), "other"), "1 in 9 is past 9%"
    assert not MIX.may_add(Counter(focus=10), "other"), "1 in 11 is just past it"
    assert MIX.may_add(Counter(focus=11), "other"), "1 in 12 is within it"
    assert not MIX.may_add(Counter(focus=98), "crypto")
    assert MIX.may_add(Counter(focus=99), "crypto"), "one in a hundred"


def test_the_policy_is_read_with_defaults():
    assert topic_mix({}) is None
    mix = topic_mix({TOPIC_MIX_KEY: {"crypto": 0.05}})
    assert mix is not None and mix.focus_terms == DEFAULT_FOCUS_TERMS
    assert (mix.crypto, mix.other) == (0.05, 0.09)
    mine = topic_mix({TOPIC_MIX_KEY: {"focus_terms": ["NVIDIA"], "crypto": 2, "other": "x"}})
    assert mine.focus_terms == ("NVIDIA",) and (mine.crypto, mine.other) == (0.01, 0.09)


def _stories(kind: str, n: int) -> list[Story]:
    return [Story(id=uuid.uuid4(), title=f"{kind} {i}") for i in range(n)]


def test_focus_first_and_another_kind_only_with_room():
    focus, other, crypto = _stories("focus", 10), _stories("other", 3), _stories("crypto", 3)
    pool = [*crypto, *other, *focus]  # the others score best
    kinds = {s.id: s.title.split()[0] for s in pool}
    chosen = choose(pool, kinds, MIX, Counter(focus=3))
    assert [s.title for s in chosen] == [f"focus {i}" for i in range(CANDIDATES)]
    chosen = choose(pool, kinds, MIX, Counter(focus=20))
    assert [kinds[s.id] for s in chosen] == ["focus"] * (CANDIDATES - 1) + ["other"]
    chosen = choose(pool, kinds, MIX, Counter(focus=200))
    assert [kinds[s.id] for s in chosen] == ["focus"] * (CANDIDATES - 2) + ["other", "crypto"]
    assert choose(other + crypto, kinds, MIX, Counter()) == [], "no focus: nothing, not filler"


async def _mixed_desk(session):
    company, project, candidates, chief = await _desk(session, stories=0)
    for title, score in (
        ("比特幣現貨 ETF 資金流入", "0.95"),
        ("富邦金取得市政大樓地上權", "0.9"),
        ("台積電 CoWoS 產能明年倍增", "0.6"),
        ("輝達發表新一代 GPU", "0.5"),
    ):
        session.add(
            Story(
                company_id=company.id, project_id=project.id, title=title,
                state=StoryState.DISCOVERED.value, score=Decimal(score), sources_count=2,
                seed={"section": "crypto"} if "比特幣" in title else {},
            )
        )  # fmt: skip
    await upsert_policy(
        session, company.id, TOPIC_MIX_KEY, {"crypto": 0.01, "other": 0.09},
        updated_by=HUMAN.as_json(),
    )  # fmt: skip
    await session.flush()
    return company, project, chief


async def test_the_chief_is_shown_the_focus_and_told_the_mix(db_session):
    company, project, chief = await _mixed_desk(db_session)
    context = await desk_context(db_session, _ctx(company, project, chief))
    assert "[focus]" in context and "台積電 CoWoS" in context and "輝達發表" in context
    assert "比特幣" not in context and "富邦金" not in context, "no room: not even shown"
    assert "Commissioned in the last 30 days: 0 focus, 0 other, 0 crypto (0 in all)." in context
    assert "anything else would be refused" in context


async def test_a_crypto_commission_is_refused_and_a_focus_one_is_not(committed):
    async with committed() as session:
        company, project, chief = await _mixed_desk(session)
        await session.commit()
        rows = await session.scalars(select(Story).where(Story.company_id == company.id))
        stories = {s.title: s.id for s in rows}
        company_id, agent_id = company.id, chief.id
    runtime = build_runtime()
    tools = ToolRegistry(committed)
    register_commission(tools, runtime.policy, runtime.workflows)

    async def commission(title):
        return await tools.invoke(
            "commission_story", {"story_id": str(stories[title])}, company_id=company_id,
            actor=Actor.agent(agent_id), tool_call_id=f"call_{uuid.uuid4().hex[:6]}",
            agent_id=agent_id,
        )  # fmt: skip

    refused = await commission("比特幣現貨 ETF 資金流入")
    assert refused.output["ok"] is False and "crypto" in refused.output["reason"]
    assert (await commission("富邦金取得市政大樓地上權")).output["ok"] is False
    assert (await commission("輝達發表新一代 GPU")).output["ok"] is True
    async with committed() as session:
        runs = (
            await session.scalars(
                select(WorkflowRun).where(
                    WorkflowRun.company_id == company_id, WorkflowRun.template_name == TEMPLATE_NAME
                )
            )
        ).all()
        assert len(runs) == 1
