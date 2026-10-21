"""D-256 with a database: the research tools (a price record, a backtest), the editor-in-chief's
commissions and ranking, and the checks each desk is held to.

Prices are stored for the test from the made-up series in ``test_research_desk``.
"""

import uuid
from decimal import Decimal
from types import SimpleNamespace

from sqlalchemy import delete, select

from autora.app import build_runtime
from autora.db.models import Task, WorkflowRun
from autora.domains.newsroom.agents.analyst import AnalysisNote, research_sides
from autora.domains.newsroom.agents.editor_in_chief import desk_context
from autora.domains.newsroom.agents.researcher import ResearchNote, computed_record_included
from autora.domains.newsroom.models import PriceBar, Story, StoryState
from autora.domains.newsroom.tools.commission import register as register_commission
from autora.domains.newsroom.tools.research import register_commissions
from autora.runtime.actor import Actor
from autora.runtime.tools import ToolRegistry
from tests.newsroom.test_editor_in_chief import _ctx, _desk
from tests.newsroom.test_research_desk import bars


async def store_prices(session, market: str, symbol: str, n: int) -> None:
    await session.execute(
        delete(PriceBar).where(PriceBar.market == market, PriceBar.symbol == symbol)
    )
    for bar in bars(n):
        session.add(
            PriceBar(
                market=market, symbol=symbol, day=bar.d, open=Decimal(f"{bar.o:.4f}"),
                high=Decimal(f"{bar.h:.4f}"), low=Decimal(f"{bar.l:.4f}"),
                close=Decimal(f"{bar.c:.4f}"), volume=int(bar.v),
                source="Tiingo" if market == "us" else "TWSE",
            )
        )  # fmt: skip
    await session.flush()


def _as_task(story_id) -> SimpleNamespace:
    """What the validators read of a run: its task's story."""
    return SimpleNamespace(task=SimpleNamespace(input={"params": {"story_id": str(story_id)}}))


# --- the researcher's records --------------------------------------------------------------------


async def test_the_price_record_is_captured_as_evidence(newsroom_room):
    async with newsroom_room.committed() as session:
        await store_prices(session, "tw", "2382", 300)
        await session.commit()

    record = await newsroom_room.call("market_snapshot", {"symbol": "2382"})

    assert record.ok, record.message
    assert "research=snapshot&" in record.output["url"]
    assert record.output["title"].startswith("本站股價數據：廣達（2382）")
    assert "收盤價" in record.output["excerpt"]


async def test_a_backtest_is_captured_and_a_short_or_unknown_stock_is_refused(newsroom_room):
    async with newsroom_room.committed() as session:
        await store_prices(session, "us", "AMD", 900)
        await store_prices(session, "us", "AAPL", 120)
        await session.commit()

    study = await newsroom_room.call("run_backtest", {"symbol": "AMD", "strategy": "breakout_20"})
    assert study.ok, study.message
    assert "research=breakout_20&" in study.output["url"]
    assert study.output["in_sample_trades"] + study.output["out_of_sample_trades"] > 0

    short = await newsroom_room.call("run_backtest", {"symbol": "AAPL", "strategy": "breakout_20"})
    assert not short.ok and "at least 400" in short.message
    unknown = await newsroom_room.call("market_snapshot", {"symbol": "ZZZZ"})
    assert not unknown.ok and "not a tracked stock" in unknown.message


async def test_a_company_report_rests_on_its_price_record(newsroom_room):
    async with newsroom_room.committed() as session:
        await store_prices(session, "tw", "2382", 300)
        story = await session.get(Story, newsroom_room.story.id)
        story.seed = {"format": "company_report", "symbol": "2382"}
        await session.commit()
    record = await newsroom_room.call("market_snapshot", {"symbol": "2382"})
    page = list(newsroom_room.evidence.values())[0]

    def note(*ids):
        return ResearchNote(
            story_id=newsroom_room.story.id,
            evidence_ids=list(ids),
            source_summaries=[{"evidence_id": i, "summary": "a source of the report"} for i in ids],
            suggested_angles=["an angle"],
        )

    async with newsroom_room.committed() as session:
        ctx = _as_task(newsroom_room.story.id)
        assert await computed_record_included(session, ctx, note(page)) == [
            "a company_report rests on the stock's computed record: call market_snapshot and "
            "list its evidence"
        ]
        assert (
            await computed_record_included(session, ctx, note(page, record.output["evidence_id"]))
            == []
        )


# --- the editor-in-chief --------------------------------------------------------------------------


async def test_the_desk_ranks_by_research_value_and_shows_the_tags(db_session):
    company, project, candidates, chief = await _desk(db_session, stories=1)  # Story 0, 0.9
    tsmc = Story(
        company_id=company.id, project_id=project.id, title="台積電法說會上調全年營收展望",
        state=StoryState.DISCOVERED.value, score=Decimal("0.5"), sources_count=2,
    )  # fmt: skip
    db_session.add(tsmc)
    await db_session.flush()

    context = await desk_context(db_session, _ctx(company, project, chief))

    assert context.index("台積電法說會") < context.index("Story 0"), "research value, not score"
    assert "research value 0.75" in context and "companies: 台積電(2330)" in context
    assert "events: earnings, guidance" in context
    assert "Story 0 · research value 0.45" in context and "no tracked company" in context
    assert "Tracked stocks (for a company report or a strategy study):" in context
    assert "- 0050 元大台灣50 (fund)" in context


async def _commissioner(committed, *, stories: int = 0):
    async with committed() as session:
        company, project, candidates, chief = await _desk(session, stories=stories)
        await store_prices(session, "tw", "2454", 500)
        await session.execute(delete(PriceBar).where(PriceBar.symbol == "2308"))
        await session.commit()
        ids = [c.id for c in candidates]
        company_id, agent_id = company.id, chief.id
    runtime = build_runtime()
    tools = ToolRegistry(committed)
    register_commission(tools, runtime.policy, runtime.workflows)
    register_commissions(tools, runtime.policy, runtime.workflows)

    async def call(tool, args):
        return await tools.invoke(
            tool, args, company_id=company_id, actor=Actor.agent(agent_id),
            tool_call_id=f"call_{uuid.uuid4().hex[:6]}", agent_id=agent_id,
        )  # fmt: skip

    return company_id, ids, call


async def test_a_company_report_is_commissioned_once_a_day_and_never_on_a_fund(committed):
    company_id, _, call = await _commissioner(committed)

    fund = await call("commission_company_report", {"symbol": "0050"})
    assert fund.output["ok"] is False and "fund" in fund.output["reason"]
    report = await call("commission_company_report", {"symbol": "2454", "angle": "第三季財報"})
    assert report.output["ok"] is True, report.output
    again = await call("commission_company_report", {"symbol": "2330"})
    assert again.output["ok"] is False and "one a day" in again.output["reason"]

    async with committed() as session:
        story = await session.get(Story, uuid.UUID(report.output["story_id"]))
        assert story.state == StoryState.IN_PRODUCTION.value
        assert story.title == "聯發科（2454）長期投資研究"
        assert story.seed["format"] == "company_report" and story.seed["section"] == "research"
        run = await session.get(WorkflowRun, uuid.UUID(report.output["workflow_run_id"]))
        tasks = (
            await session.scalars(select(Task.name).where(Task.workflow_run_id == run.id))
        ).all()
        assert "research" in tasks and "draft" in tasks, "the same desk, the same workflow"


async def test_a_strategy_study_needs_a_stored_history_and_leaves_nothing_when_refused(committed):
    company_id, _, call = await _commissioner(committed)

    short = await call("commission_strategy_study", {"symbol": "2308", "strategy": "breakout_20"})
    assert short.output["ok"] is False and "stored daily bars" in short.output["reason"]
    study = await call(
        "commission_strategy_study", {"symbol": "2454", "strategy": "trend_pullback"}
    )
    assert study.output["ok"] is True, study.output

    async with committed() as session:
        made = (
            await session.scalars(
                select(Story).where(
                    Story.company_id == company_id, Story.seed["format"].astext.is_not(None)
                )
            )
        ).all()
        assert [s.title for s in made] == ["聯發科（2454）：多頭趨勢回檔轉強策略的歷史回測"]
        assert (
            made[0].seed["strategy"] == "trend_pullback" and made[0].seed["section"] == "strategy"
        )


async def test_a_story_about_a_tracked_company_becomes_a_research_brief(committed):
    company_id, ids, call = await _commissioner(committed, stories=2)
    async with committed() as session:
        named = await session.get(Story, ids[0])
        named.title = "聯發科天璣新晶片量產"
        await session.commit()

    assert (await call("commission_story", {"story_id": str(ids[0])})).output["format"] == (
        "research_brief"
    )
    plain = await call("commission_story", {"story_id": str(ids[1])})
    assert plain.output["format"] == "news"
    async with committed() as session:
        assert (await session.get(Story, ids[0])).seed["format"] == "research_brief"
        assert "format" not in (await session.get(Story, ids[1])).seed, "news as before"


# --- the analyst and the writer -------------------------------------------------------------------


async def test_a_research_brief_s_analysis_shows_both_sides(newsroom_room):
    async with newsroom_room.committed() as session:
        story = await session.get(Story, newsroom_room.story.id)
        story.seed = {"format": "research_brief"}
        await session.commit()
    panels, cost = newsroom_room.claims["panels"], newsroom_room.claims["cost"]

    def note(**sides):
        return AnalysisNote(
            story_id=newsroom_room.story.id, claim_ids=[panels, cost], angle="一則研究角度", **sides
        )

    async with newsroom_room.committed() as session:
        ctx = _as_task(newsroom_room.story.id)
        one_sided = await research_sides(session, ctx, note(bull_claim_ids=[panels]))
        assert any("one claim against or one risk" in i for i in one_sided)
        both = note(
            bull_claim_ids=[panels],
            risk_claim_ids=[cost],
            inferences=[{"text": "面板數量與造價的關係", "based_on": [panels, cost]}],
        )
        assert await research_sides(session, ctx, both) == []
        forecast = note(
            bull_claim_ids=[panels],
            risk_claim_ids=[cost],
            inferences=[{"text": "股價可望上漲", "based_on": [panels]}],
        )
        assert any("可望" in i for i in await research_sides(session, ctx, forecast))


def _brief_draft(story_id, panels, cost, *, headings: bool) -> dict:
    outlines = {
        "zh-TW": ["事件重點", "影響哪些公司", "多空論點", "主要風險", "後續觀察"],
        "en": [
            "What happened",
            "Who is affected",
            "The case for and against",
            "Risks",
            "What to watch",
        ],
    }
    versions = []
    for lang, titles in outlines.items():
        blocks = []
        for i, title in enumerate(titles):
            if headings:
                blocks.append({"type": "heading", "text": title})
            claim = panels if i % 2 == 0 else cost
            text = f"第{i}段內容" if lang == "zh-TW" else f"Paragraph {i}"
            blocks.append({"type": "paragraph", "text": text, "claim_ids": [claim]})
        versions.append(
            {
                "lang": lang,
                "title": "流明市微電網的影響" if lang == "zh-TW" else "The grid",
                "blocks": blocks,
            }
        )
    return {"story_id": str(story_id), "versions": versions}


async def test_a_research_brief_s_draft_has_its_parts(newsroom_room):
    async with newsroom_room.committed() as session:
        story = await session.get(Story, newsroom_room.story.id)
        story.seed = {"format": "research_brief"}
        await session.commit()
    panels, cost = newsroom_room.claims["panels"], newsroom_room.claims["cost"]

    bare = await newsroom_room.call(
        "write_draft", _brief_draft(newsroom_room.story.id, panels, cost, headings=False)
    )
    assert not bare.ok and "a research_brief needs a heading" in bare.message
    whole = await newsroom_room.call(
        "write_draft", _brief_draft(newsroom_room.story.id, panels, cost, headings=True)
    )
    assert whole.ok, whole.message
