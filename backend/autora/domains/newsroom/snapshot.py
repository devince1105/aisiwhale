"""A stock's price record, computed by this newsroom (D-256): what research pieces cite for the
share price, and what they say this site does not hold.

From the site's own stored daily bars (``price_history.history``), the same numbers a stock page
draws: the latest close, the 52-week range, returns over set spans, moving averages, RSI(14),
volatility and volume. ``render`` writes them as evidence, one figure per line, and ends with
what the data cannot say — no financial statements, EPS, valuation multiples, dividends or
analysts' estimates are held here — so a report states its own gaps by quoting the record.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from autora.domains.newsroom.backtest import Bar, pct, rsi, sma

MIN_BARS = 60
SPANS = (("近 1 個月", 21), ("近 3 個月", 63), ("近 6 個月", 126), ("近 1 年", 252))
"""Trading days in each span the returns are given over."""


@dataclass(frozen=True)
class Snapshot:
    first: date
    last: date
    bars: int
    close: float
    high_52w: float
    low_52w: float
    returns: list[tuple[str, float | None]]
    averages: list[tuple[int, float | None]]
    rsi14: float | None
    volatility: float | None
    """Annualised, from the last 60 days' daily log returns."""
    volume_ratio: float | None
    """The last 20 days' average volume over the 60 before them (None: no volume)."""


class SnapshotError(ValueError):
    pass


def snapshot(bars: Sequence[Bar]) -> Snapshot:
    if len(bars) < MIN_BARS:
        raise SnapshotError(f"{len(bars)} daily bars: a snapshot needs at least {MIN_BARS}")
    closes = [b.c for b in bars]
    year = bars[-252:]
    returns = [
        (label, closes[-1] / closes[-1 - n] - 1 if len(closes) > n else None) for label, n in SPANS
    ]
    averages = [(n, sma(closes, n)[-1] if len(closes) >= n else None) for n in (20, 60, 200)]
    logs = [math.log(closes[i] / closes[i - 1]) for i in range(len(closes) - 60, len(closes))]
    mean = sum(logs) / len(logs)
    volatility = math.sqrt(sum((x - mean) ** 2 for x in logs) / (len(logs) - 1)) * math.sqrt(252)
    volumes = [b.v for b in bars]
    recent, before = volumes[-20:], volumes[-80:-20]
    volume_ratio = (
        (sum(recent) / len(recent)) / (sum(before) / len(before))
        if len(before) == 60 and sum(before) > 0 and sum(recent) > 0
        else None
    )
    return Snapshot(
        first=bars[0].d,
        last=bars[-1].d,
        bars=len(bars),
        close=closes[-1],
        high_52w=max(b.h for b in year),
        low_52w=min(b.l for b in year),
        returns=returns,
        averages=averages,
        rsi14=rsi(closes, 14)[-1],
        volatility=volatility,
        volume_ratio=volume_ratio,
    )


def _price(value: float) -> str:
    return f"{value:,.2f}"


def render(s: Snapshot, *, name: str, symbol: str, market: str, source: str | None) -> str:
    currency = "新台幣" if market == "tw" else "美元"
    lines = [
        f"本站股價數據：{name}（{symbol}），截至 {s.last.isoformat()}",
        f"本文由本站程式依 {source or '本站資料庫'} 的 {s.bars} 個交易日日線計算（"
        f"{s.first.isoformat()} 至 {s.last.isoformat()}），價格單位為{currency}。",
        "",
        f"{s.last.isoformat()} 收盤價 {_price(s.close)} {currency}。",
        f"近 52 週最高價 {_price(s.high_52w)}，最低價 {_price(s.low_52w)}；收盤價距 52 週最高價 "
        f"{pct(s.close / s.high_52w - 1)}，距 52 週最低價 {pct(s.close / s.low_52w - 1)}。",
    ]
    for label, value in s.returns:
        if value is not None:
            lines.append(f"{label}股價變動 {pct(value)}（以收盤價計，至 {s.last.isoformat()}）。")
    for n, value in s.averages:
        if value is not None:
            side = "高於" if s.close >= value else "低於"
            gap = pct(abs(s.close / value - 1))
            lines.append(f"{n} 日均線 {_price(value)}；收盤價{side} {n} 日均線 {gap}。")
    if s.rsi14 is not None:
        lines.append(f"RSI(14) 為 {s.rsi14:.1f}。")
    if s.volatility is not None:
        lines.append(f"近 60 個交易日的年化波動度為 {pct(s.volatility)}。")
    if s.volume_ratio is not None:
        lines.append(f"近 20 個交易日平均成交量為之前 60 個交易日平均的 {s.volume_ratio:.2f} 倍。")
    lines += [
        "",
        "【資料限制】",
        f"本站資料庫目前沒有 {name} 的財務報表、每股盈餘、本益比等估值倍數、股利紀錄與分析師預估；"
        "以上數字只根據股價與成交量計算。",
    ]
    if market == "tw":
        lines.append("台股價格為交易所公布的原始價格，本站已還原股票分割，但未還原股利。")
    else:
        lines.append("美股價格為 Tiingo 提供的分割與股利還原價格，依本站儲存時的版本。")
    lines.append(
        f"Price record: {symbol}, computed by this newsroom's code from {s.bars} daily bars to "
        f"{s.last.isoformat()}. This site holds no financial statements, EPS, valuation multiples, "
        "dividend records or analysts' estimates for it."
    )
    return "\n".join(lines)
