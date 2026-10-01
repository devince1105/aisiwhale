"""Brands a cover may show (D-150): the companies and coins the newsroom reports on, with the
names a story calls them by, and where their logo comes from.

A generated cover may carry the logo of what its story is about (editorial use, D-143): the logo
is handed to the image model as a reference, so it is drawn from the real thing rather than
imagined. Which brands a story is about is read off its title, summary and claims (``named``);
the cover tool accepts no other.

Logos are kept in the cover store as ``brand/<slug>.png``. Most come from Simple Icons (CC0 SVG
files, each in the brand's colour; the trademarks stay their owners'), drawn to PNG by
``scripts/brand_logos.py``. The ones Simple Icons does not carry — some owners asked it to take
theirs down — are a person's to add (an official PNG from the company's press kit) under the
same key; until then that brand is simply not offered.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Brand:
    slug: str
    name: str
    names: tuple[str, ...]
    """How a story may call it: English and Chinese names, tickers."""
    kind: str = "company"
    """company | coin"""
    simple_icons: str | None = None
    """Its Simple Icons slug, or None: the logo is added by hand."""


def _b(slug, name, *names, kind="company", si=...):
    return Brand(slug, name, (name, *names), kind, slug if si is ... else si)


BRANDS: tuple[Brand, ...] = (
    # chips and hardware
    _b("nvidia", "NVIDIA", "輝達", "NVDA"),
    _b("tsmc", "TSMC", "台積電", "2330", si=None),
    _b("amd", "AMD", "超微"),
    _b("intel", "Intel", "英特爾", "INTC"),
    _b("broadcom", "Broadcom", "博通", "AVGO"),
    _b("qualcomm", "Qualcomm", "高通", "QCOM"),
    _b("micron", "Micron", "美光", "MU", si=None),
    _b("arm", "Arm", "安謀", "ARM Holdings"),
    _b("asml", "ASML", "艾司摩爾", si=None),
    _b("mediatek", "MediaTek", "聯發科", "2454"),
    _b("samsung", "Samsung", "三星"),
    _b("foxconn", "Foxconn", "鴻海", "Hon Hai", "2317", si=None),
    # big tech
    _b("apple", "Apple", "蘋果", "AAPL"),
    _b("google", "Google", "谷歌", "Alphabet", "GOOGL", "GOOG"),
    _b("microsoft", "Microsoft", "微軟", "MSFT", si=None),
    _b("amazon", "Amazon", "亞馬遜", "AMZN", si=None),
    _b("meta", "Meta", "臉書", "Facebook", "META"),
    _b("tesla", "Tesla", "特斯拉", "TSLA"),
    _b("netflix", "Netflix", "網飛", "NFLX"),
    _b("openai", "OpenAI", si=None),
    _b("anthropic", "Anthropic"),
    _b("palantir", "Palantir", "PLTR"),
    _b("oracle", "Oracle", "甲骨文", "ORCL", si=None),
    _b("cisco", "Cisco", "思科", "CSCO"),
    _b("sony", "Sony", "索尼"),
    _b("spacex", "SpaceX"),
    _b("x", "X", "Twitter", "推特"),
    _b("alibaba", "Alibaba", "阿里巴巴", "BABA", si="alibabadotcom"),
    _b("baidu", "Baidu", "百度"),
    _b("xiaomi", "Xiaomi", "小米"),
    _b("huawei", "Huawei", "華為"),
    _b("uber", "Uber"),
    _b("shopify", "Shopify"),
    # finance
    _b("visa", "Visa", "V"),
    _b("mastercard", "Mastercard", "萬事達"),
    _b("paypal", "PayPal", "PYPL"),
    _b("goldmansachs", "Goldman Sachs", "高盛"),
    _b("bankofamerica", "Bank of America", "美國銀行"),
    _b("jpmorgan", "JPMorgan", "摩根大通", "JPM", si=None),
    _b("blackrock", "BlackRock", "貝萊德", si=None),
    _b("berkshire", "Berkshire Hathaway", "波克夏", si=None),
    _b("coinbase", "Coinbase", "COIN"),
    _b("binance", "Binance", "幣安"),
    _b("circle", "Circle", "USDC"),
    _b("tether", "Tether", "USDT", "泰達幣"),
    # coins
    _b("bitcoin", "Bitcoin", "比特幣", "BTC", kind="coin"),
    _b("ethereum", "Ethereum", "以太坊", "以太幣", "Ether", "ETH", kind="coin"),
    _b("solana", "Solana", "SOL", kind="coin"),
    _b("xrp", "XRP", "瑞波幣", kind="coin"),
    _b("dogecoin", "Dogecoin", "狗狗幣", "DOGE", kind="coin"),
    _b("cardano", "Cardano", "ADA", kind="coin"),
)

BY_SLUG = {b.slug: b for b in BRANDS}


def logo_key(slug: str) -> str:
    return f"brand/{slug}.png"


def _pattern(name: str) -> re.Pattern[str]:
    # Latin names and tickers as whole words, in their own case ("Arm" the company, not an arm;
    # "Meta", not a meta-analysis); Chinese names as they are
    if re.fullmatch(r"[A-Za-z0-9 .&-]+", name):
        return re.compile(rf"(?<![A-Za-z0-9-]){re.escape(name)}(?![A-Za-z0-9-])")
    return re.compile(re.escape(name))


_PATTERNS = {b.slug: [_pattern(n) for n in b.names if len(n) > 1] for b in BRANDS}


def named(text: str) -> list[Brand]:
    """The brands a text names, in the registry's order."""
    return [b for b in BRANDS if any(p.search(text) for p in _PATTERNS[b.slug])]
