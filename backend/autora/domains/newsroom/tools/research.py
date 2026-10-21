"""The research desk's tools (D-256).

For the researcher, two records this newsroom computes itself and captures as evidence, so the
analyst can quote them and fact-check can hold the article's numbers to them:

- ``market_snapshot``: a tracked stock's price record (``snapshot.py``) and what the site does
  not hold for it;
- ``run_backtest``: one fixed rule tested on the stock's stored daily prices (``backtest.py``).

For the editor-in-chief, two commissions no news item starts: ``commission_company_report`` and
``commission_strategy_study``. Each makes a story for the piece — its format, stock and rule in
``seed`` — and puts the desk to work on it as ``commission_story`` does (``put_to_work``): the
same mix, the same company cap, the same workflow, review and approval.

Only the strip's stocks (``holdings.STOCKS``) are researched: they are the ones whose prices the
site keeps every day. A stock without enough stored history is refused, never filled in.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from autora.domains.newsroom import backtest, holdings, research, snapshot
from autora.domains.newsroom.models import Story, StoryState
from autora.domains.newsroom.tools.commission import put_to_work
from autora.domains.newsroom.tools.evidence import EXCERPT, READ_NOTE, capture_text
from autora.infra.blobstore import BlobStore
from autora.runtime.dag import WorkflowEngine
from autora.runtime.events.catalog import ProducedRef
from autora.runtime.models.embeddings import Embedder
from autora.runtime.policy import PolicyEngine
from autora.runtime.tools import ToolContext, ToolFn, ToolRegistry, ToolResult

SITE = "https://aisiwhale.com"
"""Where a computed record points a reader: the stock's own page, which draws the same prices."""

ETFS = frozenset({"QQQ", "VOO"})
"""The strip's funds besides Taiwan's 00 codes: a strategy may be tested on them, a company report
is not written about them."""

REPORT_EVERY = timedelta(days=30)
STUDY_EVERY = timedelta(days=90)
PER_DAY = timedelta(hours=20)
"""At most one company report and one strategy study commissioned in this long (a day's plan)."""

StrategyName = Literal["breakout_20", "trend_pullback", "range_reversion"]


class StockError(Exception):
    retryable = False


def tracked(symbol: str) -> holdings.Stock:
    stock = holdings.STOCKS.get(symbol.strip().upper())
    if stock is None:
        raise StockError(f"{symbol!r} is not a tracked stock; one of {', '.join(holdings.STOCKS)}")
    return stock


def is_fund(stock: holdings.Stock) -> bool:
    return stock.symbol in ETFS or stock.symbol.startswith("00")


async def stored_bars(ctx: ToolContext, stock: holdings.Stock) -> tuple[list[backtest.Bar], str]:
    """The stock's stored daily bars, split-adjusted as its page draws them, and their source."""
    from autora.domains.newsroom.price_history import history

    found = await history(ctx.session, stock.market, stock.symbol)
    bars = [backtest.Bar(b.d, b.o, b.h, b.l, b.c, float(b.v)) for b in found.bars if b.c > 0]
    return bars, found.source or ""


def _page(stock: holdings.Stock, what: str, on: str) -> str:
    return f"{SITE}/news/zh-TW/stocks/{stock.symbol}?research={what}&as_of={on}"


# --- the researcher's records ---------------------------------------------------------------------


class SnapshotArgs(BaseModel):
    symbol: str = Field(min_length=1, max_length=10, description="A tracked stock: 2330, NVDA…")


class BacktestArgs(BaseModel):
    symbol: str = Field(min_length=1, max_length=10, description="A tracked stock or ETF.")
    strategy: StrategyName = Field(description="The rule to test (the story says which).")


def market_snapshot_tool(
    blobs: BlobStore, embedder: Embedder, clock: Callable[[], datetime]
) -> ToolFn:
    async def market_snapshot(args: SnapshotArgs, ctx: ToolContext) -> ToolResult:
        stock = tracked(args.symbol)
        bars, source = await stored_bars(ctx, stock)
        try:
            record = snapshot.snapshot(bars)
        except snapshot.SnapshotError as error:
            raise StockError(f"{stock.symbol}: {error}; the site has not stored enough") from error
        text = snapshot.render(
            record, name=stock.zh, symbol=stock.symbol, market=stock.market, source=source
        )
        on = record.last.isoformat()
        evidence, reused = await capture_text(
            ctx,
            url=_page(stock, "snapshot", on),
            final_url=_page(stock, "snapshot", on),
            title=f"本站股價數據：{stock.zh}（{stock.symbol}），截至 {on}",
            content_type="text/plain; charset=utf-8",
            language="zh-TW",
            text=text,
            truncated=False,
            snapshot=text.encode(),
            blobs=blobs,
            embedder=embedder,
            now=clock(),
        )
        return ToolResult(
            output={
                "evidence_id": str(evidence.id),
                "url": evidence.url,
                "title": evidence.title,
                "as_of": on,
                "reused": reused,
                "excerpt": evidence.extracted_text[:EXCERPT],
                "note": READ_NOTE,
            },
            summary=f"{'reused' if reused else 'captured'} price record {evidence.id} "
            f"({stock.symbol} to {on})",
            produced=[ProducedRef(type="evidence", id=evidence.id)],
        )

    return market_snapshot


def run_backtest_tool(
    blobs: BlobStore, embedder: Embedder, clock: Callable[[], datetime]
) -> ToolFn:
    async def run_backtest(args: BacktestArgs, ctx: ToolContext) -> ToolResult:
        stock = tracked(args.symbol)
        bars, source = await stored_bars(ctx, stock)
        try:
            result = backtest.run(
                bars, args.strategy, backtest.costs_for(stock.market, stock.symbol)
            )
        except backtest.BacktestError as error:
            raise StockError(f"{stock.symbol}: {error}") from error
        text = backtest.render(
            result, name=stock.zh, symbol=stock.symbol, market=stock.market, source=source
        )
        on = result.last.isoformat()
        evidence, reused = await capture_text(
            ctx,
            url=_page(stock, args.strategy, on),
            final_url=_page(stock, args.strategy, on),
            title=f"本站策略研究：{stock.zh}（{stock.symbol}）{result.strategy.zh}，"
            f"{result.first.isoformat()} 至 {on}",
            content_type="text/plain; charset=utf-8",
            language="zh-TW",
            text=text,
            truncated=False,
            snapshot=text.encode(),
            blobs=blobs,
            embedder=embedder,
            now=clock(),
        )
        ins, outs = result.in_sample, result.out_sample
        return ToolResult(
            output={
                "evidence_id": str(evidence.id),
                "url": evidence.url,
                "title": evidence.title,
                "bars": result.bars,
                "in_sample_trades": ins.trades,
                "out_of_sample_trades": outs.trades,
                "reused": reused,
                "excerpt": evidence.extracted_text[:EXCERPT],
                "note": READ_NOTE,
            },
            summary=f"{'reused' if reused else 'captured'} backtest {evidence.id} "
            f"({stock.symbol}, {args.strategy}: {ins.trades}+{outs.trades} trades)",
            produced=[ProducedRef(type="evidence", id=evidence.id)],
        )

    return run_backtest


# --- the editor-in-chief's commissions ------------------------------------------------------------


class CompanyReportArgs(BaseModel):
    symbol: str = Field(min_length=1, max_length=10, description="A tracked company's stock.")
    angle: str | None = Field(
        default=None, max_length=300, description="Why now, for the researcher (results, news)."
    )


class StrategyStudyArgs(BaseModel):
    symbol: str = Field(min_length=1, max_length=10, description="A tracked stock or ETF.")
    strategy: StrategyName
    angle: str | None = Field(default=None, max_length=300)


async def _recent(ctx: ToolContext, fmt: str, since: timedelta, **seed: str) -> Story | None:
    """The latest story of this format (and stock, rule) commissioned in the span and not
    dropped: a piece the desk gave up on may be tried again."""
    query = select(Story).where(
        Story.company_id == ctx.company_id,
        Story.seed[research.FORMAT].astext == fmt,
        Story.created_at >= datetime.now(UTC) - since,
        Story.state.in_(
            [StoryState.SELECTED.value, StoryState.IN_PRODUCTION.value, StoryState.PUBLISHED.value]
        ),
    )
    for key, value in seed.items():
        query = query.where(Story.seed[key].astext == value)
    return await ctx.session.scalar(query.order_by(Story.created_at.desc()).limit(1))


def _refused(reason: str) -> ToolResult:
    return ToolResult(output={"ok": False, "reason": reason}, summary=reason[:120])


async def _new_story(ctx: ToolContext, *, title: str, summary: str, seed: dict) -> Story:
    story = Story(
        company_id=ctx.company_id,
        title=title,
        summary=summary,
        state=StoryState.DISCOVERED.value,
        score=0,
        seed=seed,
    )
    ctx.session.add(story)
    await ctx.session.flush()
    return story


async def _commission(
    ctx: ToolContext,
    story: Story,
    *,
    policy: PolicyEngine,
    workflows: WorkflowEngine,
    angle: str | None,
    fmt: str,
) -> ToolResult:
    """``put_to_work`` for a story made for the piece: refused (the mix, the company's cap), the
    story goes again — it was never a candidate, and must not become one."""
    result = await put_to_work(ctx, story, policy=policy, workflows=workflows, angle=angle, fmt=fmt)
    if not result.output.get("ok"):
        await ctx.session.delete(story)
        await ctx.session.flush()
    return result


def register_commissions(
    registry: ToolRegistry, policy: PolicyEngine, workflows: WorkflowEngine
) -> None:
    async def commission_company_report(args: CompanyReportArgs, ctx: ToolContext) -> ToolResult:
        stock = tracked(args.symbol)
        if is_fund(stock):
            return _refused(f"{stock.symbol} is a fund: a company report is about a company")
        if await _recent(ctx, "company_report", PER_DAY):
            return _refused("a company report was commissioned today already: one a day")
        if earlier := await _recent(ctx, "company_report", REPORT_EVERY, symbol=stock.symbol):
            return _refused(
                f"{stock.zh} had a company report commissioned on "
                f"{earlier.created_at.date().isoformat()}: one in {REPORT_EVERY.days} days"
            )
        story = await _new_story(
            ctx,
            title=f"{stock.zh}（{stock.symbol}）長期投資研究",
            summary=args.angle or f"{stock.zh}（{stock.en}）的營運、財務、估值與多空論點整理",
            seed={
                research.FORMAT: "company_report",
                research.SYMBOL: stock.symbol,
                research.MARKET: stock.market,
                "section": research.RESEARCH_SECTION,
                "query": f"{stock.en} quarterly results investor relations",
            },
        )
        return await _commission(
            ctx, story, policy=policy, workflows=workflows, angle=args.angle, fmt="company_report"
        )

    async def commission_strategy_study(args: StrategyStudyArgs, ctx: ToolContext) -> ToolResult:
        stock = tracked(args.symbol)
        rule = backtest.STRATEGIES[args.strategy]
        if await _recent(ctx, "strategy_study", PER_DAY):
            return _refused("a strategy study was commissioned today already: one a day")
        if earlier := await _recent(
            ctx, "strategy_study", STUDY_EVERY, symbol=stock.symbol, strategy=args.strategy
        ):
            return _refused(
                f"{rule.zh} on {stock.zh} was studied from {earlier.created_at.date().isoformat()}"
                f": one in {STUDY_EVERY.days} days"
            )
        bars, _ = await stored_bars(ctx, stock)
        if len(bars) < backtest.MIN_BARS:
            return _refused(
                f"{stock.symbol} has {len(bars)} stored daily bars; a study needs "
                f"{backtest.MIN_BARS}. Choose a stock with a longer history."
            )
        story = await _new_story(
            ctx,
            title=f"{stock.zh}（{stock.symbol}）：{rule.zh}策略的歷史回測",
            summary=args.angle or f"以本站程式回測「{rule.zh}」規則在{stock.zh}的歷史表現",
            seed={
                research.FORMAT: "strategy_study",
                research.SYMBOL: stock.symbol,
                research.MARKET: stock.market,
                research.STRATEGY: args.strategy,
                "section": research.STRATEGY_SECTION,
            },
        )
        return await _commission(
            ctx, story, policy=policy, workflows=workflows, angle=args.angle, fmt="strategy_study"
        )

    registry.tool(
        "commission_company_report",
        description=(
            "Commission a long-term research report on a tracked company (D-256): its business, "
            "results, valuation context, the case for and against, risks and data limits. One a "
            "day; one per company in 30 days."
        ),
        side_effect="write",
        retryable=False,
    )(commission_company_report)
    registry.tool(
        "commission_strategy_study",
        description=(
            "Commission a strategy study (D-256): one fixed rule (breakout_20, trend_pullback, "
            "range_reversion) backtested on a tracked stock's stored prices by the newsroom's "
            "code, in-sample and out-of-sample. History only, never a current signal. One a day."
        ),
        side_effect="write",
        retryable=False,
    )(commission_strategy_study)


async def tracked_overview(session: AsyncSession, company_id: uuid.UUID) -> list[str]:
    """For the editor-in-chief: what each tracked stock had lately, so she picks what is due."""
    since = datetime.now(UTC) - STUDY_EVERY
    rows = (
        await session.execute(
            select(
                Story.seed[research.SYMBOL].astext,
                Story.seed[research.FORMAT].astext,
                Story.created_at,
            )
            .where(
                Story.company_id == company_id,
                Story.seed[research.FORMAT].astext.in_(["company_report", "strategy_study"]),
                Story.created_at >= since,
            )
            .order_by(Story.created_at)
        )
    ).all()
    last = {(symbol, fmt): when.date().isoformat() for symbol, fmt, when in rows}  # latest wins
    lines = []
    for stock in holdings.STOCKS.values():
        report = last.get((stock.symbol, "company_report"))
        study = last.get((stock.symbol, "strategy_study"))
        kind = "fund" if is_fund(stock) else "company"
        lines.append(
            f"- {stock.symbol} {stock.zh} ({kind}) · last report: {report or 'none in 90 days'}"
            f" · last strategy study: {study or 'none in 90 days'}"
        )
    return lines


def register(
    registry: ToolRegistry,
    blobs: BlobStore,
    embedder: Embedder,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> None:
    registry.tool(
        "market_snapshot",
        description=(
            "Capture a tracked stock's price record as evidence (D-256): latest close, 52-week "
            "range, returns, moving averages, RSI, volatility, volume — computed by this "
            "newsroom from its stored prices — and what data the site does not hold for it."
        ),
        side_effect="write",
        timeout_s=30.0,
        retryable=True,
    )(market_snapshot_tool(blobs, embedder, clock))
    registry.tool(
        "run_backtest",
        description=(
            "Backtest one fixed rule on a tracked stock's stored daily prices (D-256) and capture "
            "the result as evidence: rules, costs, in-sample and out-of-sample trades, win rate, "
            "expectancy, drawdown and buy-and-hold."
        ),
        side_effect="write",
        timeout_s=60.0,
        retryable=True,
    )(run_backtest_tool(blobs, embedder, clock))
