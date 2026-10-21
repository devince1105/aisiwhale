"""Strategy studies (D-256): a fixed trading rule tested on a stock's stored daily prices.

The rules are set here, before any result is seen, and are not tuned per stock: a study reports
how one rule did, not the best of many tries. Each is computed by code, not judged by a model —
the model only reads the evidence ``render`` writes, and fact-check holds its numbers to it.

**How a test runs**

- A signal is read at a day's close; the trade happens at the next day's open. One position at
  a time, long only, all in or all out; no leverage, no shorting.
- Costs are charged on every buy and sell (``Costs``): Taiwan's broker fee both ways and its
  securities transaction tax on the sale (an ETF's lower rate for codes starting ``00``), an
  assumed slippage both ways in both markets. They are assumptions, and the evidence says so.
- The history is split by date: the first ``IN_SAMPLE`` share of the days in-sample, the rest
  out-of-sample. A trade belongs to the period it was entered in; each period's drawdown is on
  its own marked-to-market equity, starting at 1.
- Indicators need ``WARM_UP`` days before the first signal; a history shorter than
  ``MIN_BARS`` is not tested.

**What the prices are.** The site's own stored bars (``price_history.history``): Taiwan's are
the exchange's, split-adjusted by the site but **not** for dividends, so a study around ex-dates
reads a dividend as a fall; the US's are Tiingo's split- and dividend-adjusted closes as they
were stored. ``render`` says which.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Literal

IN_SAMPLE = 0.7
WARM_UP = 200
MIN_BARS = 400
SMALL_SAMPLE = 20
"""Fewer trades than this in a period: its statistics say little, and the evidence says so."""


@dataclass(frozen=True)
class Bar:
    d: date
    o: float
    h: float
    l: float  # noqa: E741 — as price_history.PublicBar names it
    c: float
    v: float


# --- indicators ---------------------------------------------------------------------------------


def sma(values: Sequence[float], n: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    total = 0.0
    for i, value in enumerate(values):
        total += value
        if i >= n:
            total -= values[i - n]
        if i >= n - 1:
            out[i] = total / n
    return out


def stdev(values: Sequence[float], n: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    for i in range(n - 1, len(values)):
        window = values[i - n + 1 : i + 1]
        mean = sum(window) / n
        out[i] = math.sqrt(sum((x - mean) ** 2 for x in window) / n)
    return out


def rsi(closes: Sequence[float], n: int = 14) -> list[float | None]:
    """Wilder's RSI: the first average over ``n`` changes, then smoothed."""
    out: list[float | None] = [None] * len(closes)
    if len(closes) <= n:
        return out
    gains = [max(closes[i] - closes[i - 1], 0.0) for i in range(1, len(closes))]
    losses = [max(closes[i - 1] - closes[i], 0.0) for i in range(1, len(closes))]
    gain, loss = sum(gains[:n]) / n, sum(losses[:n]) / n
    for i in range(n, len(closes)):
        if i > n:
            gain = (gain * (n - 1) + gains[i - 1]) / n
            loss = (loss * (n - 1) + losses[i - 1]) / n
        out[i] = 100.0 if loss == 0 else 100.0 - 100.0 / (1.0 + gain / loss)
    return out


def atr(bars: Sequence[Bar], n: int = 14) -> list[float | None]:
    """Wilder's average true range."""
    out: list[float | None] = [None] * len(bars)
    ranges = [bars[0].h - bars[0].l] + [
        max(b.h - b.l, abs(b.h - p.c), abs(b.l - p.c)) for p, b in zip(bars, bars[1:], strict=False)
    ]
    if len(bars) < n:
        return out
    value = sum(ranges[:n]) / n
    out[n - 1] = value
    for i in range(n, len(bars)):
        value = (value * (n - 1) + ranges[i]) / n
        out[i] = value
    return out


def highest(values: Sequence[float], n: int) -> list[float | None]:
    """The highest of the ``n`` values *before* each one (today's is not its own breakout)."""
    return [max(values[i - n : i]) if i >= n else None for i in range(len(values))]


def lowest(values: Sequence[float], n: int) -> list[float | None]:
    return [min(values[i - n : i]) if i >= n else None for i in range(len(values))]


# --- the rules ------------------------------------------------------------------------------------

StrategyKey = Literal["breakout_20", "trend_pullback", "range_reversion"]


@dataclass(frozen=True)
class Strategy:
    key: StrategyKey
    zh: str
    en: str
    entry_zh: str
    exit_zh: str
    entry_en: str
    exit_en: str


STRATEGIES: dict[str, Strategy] = {
    s.key: s
    for s in (
        Strategy(
            "breakout_20",
            "20 日區間突破",
            "20-day breakout",
            "收盤價高於前 20 個交易日的最高價，且成交量高於前 20 日平均的 1.5 倍（沒有成交量的"
            "標的不看量）",
            "收盤價低於前 10 個交易日的最低價，或收盤價低於進場價減 2 倍 ATR(14)",
            "the close is above the highest high of the previous 20 days, on volume above 1.5 "
            "times its 20-day average (where there is volume)",
            "the close is below the lowest low of the previous 10 days, or below the entry price "
            "less 2 x ATR(14)",
        ),
        Strategy(
            "trend_pullback",
            "多頭趨勢回檔轉強",
            "Trend pullback",
            "50 日均線在 200 日均線之上，且 RSI(14) 由 40 以下回升到 40 以上",
            "收盤價跌破 200 日均線、RSI(14) 高於 70，或收盤價低於進場價減 2 倍 ATR(14)",
            "the 50-day average is above the 200-day, and RSI(14) climbs back above 40 from below",
            "the close falls below the 200-day average, RSI(14) is above 70, or the close is below "
            "the entry price less 2 x ATR(14)",
        ),
        Strategy(
            "range_reversion",
            "區間均值回歸",
            "Range mean reversion",
            "50 日均線 20 個交易日內變動不到 2%（盤整），且收盤價低於 20 日均線減 2 倍標準差",
            "收盤價回到 20 日均線以上、持有滿 10 個交易日，或收盤價低於進場價的 92%",
            "the 50-day average has moved less than 2% over 20 days (a range), and the close is "
            "below the 20-day average less 2 standard deviations",
            "the close is back above the 20-day average, 10 days have passed, or the close is "
            "below 92% of the entry price",
        ),
    )
}


@dataclass(frozen=True)
class Indicators:
    sma20: list[float | None]
    sma50: list[float | None]
    sma200: list[float | None]
    sd20: list[float | None]
    rsi14: list[float | None]
    atr14: list[float | None]
    high20: list[float | None]
    low10: list[float | None]
    vol20: list[float | None]


def indicators(bars: Sequence[Bar]) -> Indicators:
    closes = [b.c for b in bars]
    return Indicators(
        sma20=sma(closes, 20),
        sma50=sma(closes, 50),
        sma200=sma(closes, 200),
        sd20=stdev(closes, 20),
        rsi14=rsi(closes, 14),
        atr14=atr(bars, 14),
        high20=highest([b.h for b in bars], 20),
        low10=lowest([b.l for b in bars], 10),
        vol20=_vol_avg(bars),
    )


def _vol_avg(bars: Sequence[Bar]) -> list[float | None]:
    """The average volume of the 20 days before each one."""
    volumes = [b.v for b in bars]
    out: list[float | None] = [None] * len(bars)
    for i in range(20, len(bars)):
        out[i] = sum(volumes[i - 20 : i]) / 20
    return out


def _enter(key: str, i: int, bars: Sequence[Bar], x: Indicators) -> bool:
    b = bars[i]
    if key == "breakout_20":
        if x.high20[i] is None or b.c <= x.high20[i]:
            return False
        if b.v and x.vol20[i]:
            return b.v > 1.5 * x.vol20[i]
        return True
    if key == "trend_pullback":
        prev, now = x.rsi14[i - 1], x.rsi14[i]
        return (
            None not in (x.sma50[i], x.sma200[i], prev, now)
            and x.sma50[i] > x.sma200[i]  # type: ignore[operator]
            and prev < 40 <= now  # type: ignore[operator]
        )
    if key == "range_reversion":
        then = x.sma50[i - 20] if i >= 20 else None
        if None in (x.sma50[i], then, x.sma20[i], x.sd20[i]):
            return False
        flat = abs(x.sma50[i] / then - 1) < 0.02  # type: ignore[operator]
        return flat and b.c < x.sma20[i] - 2 * x.sd20[i]  # type: ignore[operator]
    raise ValueError(f"no strategy {key}")


def _leave(key: str, i: int, bars: Sequence[Bar], x: Indicators, entry: float, held: int) -> bool:
    b = bars[i]
    stop = x.atr14[i]
    if key == "breakout_20":
        return (x.low10[i] is not None and b.c < x.low10[i]) or (
            stop is not None and b.c < entry - 2 * stop
        )
    if key == "trend_pullback":
        return (
            (x.sma200[i] is not None and b.c < x.sma200[i])
            or (x.rsi14[i] is not None and x.rsi14[i] > 70)
            or (stop is not None and b.c < entry - 2 * stop)
        )
    if key == "range_reversion":
        return (x.sma20[i] is not None and b.c >= x.sma20[i]) or held >= 10 or b.c < 0.92 * entry
    raise ValueError(f"no strategy {key}")


# --- costs ----------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Costs:
    buy: float
    """A fraction of the price, paid on every buy."""
    sell: float
    """A fraction of the price, paid on every sale (fees and taxes)."""
    note_zh: str
    note_en: str


TW_FEE = 0.001425
TW_TAX = 0.003
TW_ETF_TAX = 0.001
SLIPPAGE = 0.0005


def costs_for(market: str, symbol: str) -> Costs:
    """The assumed costs of one round trip; stated, never hidden in the results."""
    if market == "tw":
        tax = TW_ETF_TAX if symbol.startswith("00") else TW_TAX
        kind_zh = "ETF 證交稅 0.1%" if symbol.startswith("00") else "證交稅 0.3%"
        kind_en = "ETF transaction tax 0.1%" if symbol.startswith("00") else "transaction tax 0.3%"
        return Costs(
            buy=TW_FEE + SLIPPAGE,
            sell=TW_FEE + tax + SLIPPAGE,
            note_zh=f"買賣各付手續費 0.1425%（未計折扣），賣出另付{kind_zh}，買賣各假設滑價 0.05%",
            note_en=f"a 0.1425% broker fee each way (no discount), a {kind_en} on the sale, and an "
            "assumed 0.05% slippage each way",
        )
    return Costs(
        buy=SLIPPAGE,
        sell=SLIPPAGE,
        note_zh="不計手續費（多數美股券商零佣金），買賣各假設滑價 0.05%",
        note_en="no commission (most US brokers charge none), an assumed 0.05% slippage each way",
    )


# --- the test -------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Trade:
    entered: date
    entry: float
    left: date
    exit: float
    days: int
    ret: float
    """After costs: what one unit of money became, less one."""


@dataclass(frozen=True)
class Stats:
    start: date
    end: date
    days: int
    trades: int
    wins: int
    win_rate: float | None
    avg_win: float | None
    avg_loss: float | None
    payoff: float | None
    expectancy: float | None
    total_return: float
    max_drawdown: float
    exposure: float
    buy_hold: float
    avg_days: float | None


@dataclass(frozen=True)
class Result:
    strategy: Strategy
    costs: Costs
    bars: int
    first: date
    last: date
    split: date
    """The first out-of-sample day."""
    in_sample: Stats
    out_sample: Stats
    trades: list[Trade] = field(default_factory=list)


class BacktestError(ValueError):
    pass


def run(bars: Sequence[Bar], strategy_key: str, costs: Costs) -> Result:
    """Test one rule on the bars (oldest first)."""
    strategy = STRATEGIES.get(strategy_key)
    if strategy is None:
        raise BacktestError(f"no strategy {strategy_key!r}: one of {', '.join(STRATEGIES)}")
    if len(bars) < MIN_BARS:
        raise BacktestError(
            f"{len(bars)} daily bars: a study needs at least {MIN_BARS} (about 20 months)"
        )
    x = indicators(bars)
    split_at = int(len(bars) * IN_SAMPLE)
    trades: list[Trade] = []
    held_on = [False] * len(bars)  # in the market at the day's close
    position: tuple[int, float] | None = None  # (the day entered, the price paid)
    pending: Literal["buy", "sell"] | None = None
    for i in range(len(bars)):
        bar = bars[i]
        if pending == "buy" and position is None:
            position = (i, bar.o * (1 + costs.buy))
        elif pending == "sell" and position is not None:
            start, paid = position
            got = bar.o * (1 - costs.sell)
            trades.append(Trade(bars[start].d, paid, bar.d, got, i - start, got / paid - 1))
            position = None
        pending = None
        held_on[i] = position is not None
        if i < WARM_UP or i == len(bars) - 1:
            continue
        if position is None:
            if _enter(strategy.key, i, bars, x):
                pending = "buy"
        elif _leave(strategy.key, i, bars, x, bars[position[0]].o, i - position[0]):
            pending = "sell"
    if position is not None:  # still in at the end: closed at the last close, so it counts
        start, paid = position
        got = bars[-1].c * (1 - costs.sell)
        trades.append(
            Trade(bars[start].d, paid, bars[-1].d, got, len(bars) - 1 - start, got / paid - 1)
        )

    return Result(
        strategy=strategy,
        costs=costs,
        bars=len(bars),
        first=bars[0].d,
        last=bars[-1].d,
        split=bars[split_at].d,
        in_sample=_stats(bars, 0, split_at, trades, held_on, costs),
        out_sample=_stats(bars, split_at, len(bars), trades, held_on, costs),
        trades=trades,
    )


def _stats(
    bars: Sequence[Bar],
    lo: int,
    hi: int,
    trades: list[Trade],
    held_on: list[bool],
    costs: Costs,
) -> Stats:
    """One period's statistics: the trades entered in it, and its own equity curve."""
    start, end = bars[lo].d, bars[hi - 1].d
    mine = [t for t in trades if start <= t.entered <= end]
    wins = [t.ret for t in mine if t.ret > 0]
    losses = [t.ret for t in mine if t.ret <= 0]
    total = 1.0
    for t in mine:
        total *= 1 + t.ret
    # marked to market each day: bought at the open, held to the close, sold at the open
    equity, peak, drawdown = 1.0, 1.0, 0.0
    first = max(lo, WARM_UP)
    for i in range(first + 1, hi):
        before, now = held_on[i - 1], held_on[i]
        if before and now:
            equity *= bars[i].c / bars[i - 1].c
        elif now:
            equity *= bars[i].c / (bars[i].o * (1 + costs.buy))
        elif before:
            equity *= bars[i].o * (1 - costs.sell) / bars[i - 1].c
        peak = max(peak, equity)
        drawdown = min(drawdown, equity / peak - 1)
    in_market = sum(1 for i in range(first, hi) if held_on[i])
    span = max(1, hi - first)
    hold = bars[hi - 1].c * (1 - costs.sell) / (bars[first].o * (1 + costs.buy)) - 1
    return Stats(
        start=start,
        end=end,
        days=hi - lo,
        trades=len(mine),
        wins=len(wins),
        win_rate=len(wins) / len(mine) if mine else None,
        avg_win=sum(wins) / len(wins) if wins else None,
        avg_loss=sum(losses) / len(losses) if losses else None,
        payoff=(sum(wins) / len(wins)) / abs(sum(losses) / len(losses))
        if wins and losses and sum(losses)
        else None,
        expectancy=sum(t.ret for t in mine) / len(mine) if mine else None,
        total_return=total - 1,
        max_drawdown=drawdown,
        exposure=in_market / span,
        buy_hold=hold,
        avg_days=sum(t.days for t in mine) / len(mine) if mine else None,
    )


# --- the evidence ---------------------------------------------------------------------------------


def pct(value: float | None, places: int = 1) -> str:
    return "無" if value is None else f"{value * 100:.{places}f}%"


def _period(name: str, s: Stats) -> list[str]:
    lines = [
        f"{name}：{s.start.isoformat()} 至 {s.end.isoformat()}，共 {s.days} 個交易日。",
        f"{name}交易次數：{s.trades} 筆；獲利 {s.wins} 筆；勝率 {pct(s.win_rate)}。",
        f"{name}平均每筆獲利 {pct(s.avg_win, 2)}；平均每筆虧損 {pct(s.avg_loss, 2)}；"
        f"盈虧比 {'無' if s.payoff is None else f'{s.payoff:.2f}'}。",
        f"{name}每筆平均報酬（期望值）{pct(s.expectancy, 2)}；平均持有 "
        f"{'無' if s.avg_days is None else f'{s.avg_days:.1f}'} 個交易日。",
        f"{name}策略累計報酬 {pct(s.total_return)}；最大回撤 {pct(s.max_drawdown)}；"
        f"持有部位的天數占 {pct(s.exposure)}。",
        f"{name}同期買進持有報酬 {pct(s.buy_hold)}（同樣扣除一次買賣成本）。",
    ]
    if s.trades < SMALL_SAMPLE:
        lines.append(f"{name}只有 {s.trades} 筆交易，少於 {SMALL_SAMPLE} 筆：統計結果的可信度低。")
    return lines


def render(result: Result, *, name: str, symbol: str, market: str, source: str | None) -> str:
    """The study as evidence: every figure the article may state, one per line, in the words a
    claim can quote."""
    s = result.strategy
    adjusted = (
        "台股價格為交易所公布的原始價格，本站已還原股票分割，但未還原股利：除息日的價格下跌會被"
        "當成一般下跌計算。"
        if market == "tw"
        else "美股價格為 Tiingo 提供的分割與股利還原價格，依本站儲存時的版本。"
    )
    lines = [
        f"本站策略研究：{name}（{symbol}）— {s.zh}（{s.en}）",
        f"本文由本站程式依 {source or '本站資料庫'} 的 {result.bars} 個交易日日線計算，期間為 "
        f"{result.first.isoformat()} 至 {result.last.isoformat()}。所有數字都是歷史回測結果，"
        "不代表未來表現，也不是交易建議。",
        "",
        "【策略規則】",
        f"進場條件：{s.entry_zh}。",
        f"出場條件：{s.exit_zh}。",
        "訊號以當日收盤判斷，次一交易日開盤成交；一次只持有一個部位，只做多，不融資、不放空。",
        f"規則在看到結果之前就已固定，沒有針對 {symbol} 調整參數。",
        "",
        "【資料與成本假設】",
        f"成本假設：{result.costs.note_zh}。",
        adjusted,
        f"樣本切分：前 {IN_SAMPLE:.0%} 的交易日為樣本內，之後為樣本外；樣本外自 "
        f"{result.split.isoformat()} 起。指標需要 {WARM_UP} 個交易日暖機，暖機期間不交易。",
        "",
        "【樣本內結果】",
        *_period("樣本內", result.in_sample),
        "",
        "【樣本外結果】",
        *_period("樣本外", result.out_sample),
        "",
        "【限制】",
        "回測只看單一標的、固定規則與假設成本；實際成交價、手續費折扣、稅負與流動性都可能不同。",
        "過去的回測結果不代表這條規則未來仍然有效。",
        "",
        f"Strategy study: {s.en} on {symbol}, computed by this newsroom's code from "
        f"{result.bars} daily bars ({result.first.isoformat()} to {result.last.isoformat()}). "
        f"Entry: {s.entry_en}. Exit: {s.exit_en}. Costs: {result.costs.note_en}.",
    ]
    return "\n".join(lines)
