"""艾矽鯨 covers NVIDIA, TSMC and the AI supply chain (D-253): its mission, its topic mix, and its
sources — the focus's six added, what it stopped covering paused, crypto searched once a day

The newsroom's sources and mission are ``markets.py``'s, brought to a database by
``seed_markets``; production cannot be reached for that from here (the network refuses 5432), so
this migration does for 艾矽鯨 what seeding would. A database without the company (the tests', a
developer's) is left alone. The values are written out, not imported: a migration says what it
did, whatever the code says later (``test_markets`` checks they are the code's today).

Paused, not deleted: their items, stories and articles stay. Down: the old mission, no mix, the
paused back on, the six added paused (a source with items cannot go).

Revision ID: 0083
Revises: 0082
Create Date: 2026-10-14 09:00:00+00:00
"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0083"
down_revision: str | None = "0082"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SLUG = "aisiwhale"

MISSION = (
    "用附原始出處的中英雙語報導，聚焦輝達（NVIDIA）、台積電與它們周邊的 AI 供應鏈"
    "（AI 伺服器、GPU、HBM、先進封裝、資料中心）；台股、美股與大型投資人的持股，"
    "以和 AI 相關的為主；加密貨幣只報導重大的監管與市場事件。"
    "只報導事實與別人說的話，不提供投資建議。"
)
OLD_MISSION = (
    "用附原始出處的中英雙語報導，追蹤 AI 與半導體產業的動向、大型投資人的持股變化，"
    "台股、美股裡的 AI 科技公司，名人（如美國總統、國會議員）依法申報的持股與交易，"
    "加密貨幣的監管、ETF 與市場動態，"
    "以及黃金、期貨（金屬、能源、農產品）與外匯（臺灣銀行掛牌的外幣）的價格與供需；"
    "只報導事實與別人說的話，不提供投資建議。"
)

FOCUS_TERMS = [
    *("NVIDIA", "Nvidia", "輝達", "黃仁勳", "TSMC", "台積電", "AI 伺服器", "AI伺服器", "GPU"),
    *("HBM", "CoWoS", "先進封裝", "資料中心", "data center", "鴻海", "Foxconn", "廣達", "緯創"),
    *("緯穎", "世芯", "創意電子", "日月光", "SK hynix", "SK 海力士", "Micron", "美光", "AMD"),
    *("Broadcom", "博通", "ASML", "AI chip", "AI 晶片"),
]
TOPIC_MIX = {"focus_terms": FOCUS_TERMS, "crypto": 0.01, "other": 0.09}
ACTOR = {"kind": "system", "id": "migration:0083"}

TW_NEWS = [
    "cna.com.tw",
    "cnyes.com",
    "money.udn.com",
    "ctee.com.tw",
    "moneydj.com",
    "ec.ltn.com.tw",
]


def _search(query: str, section: str, domains: list[str], language: str = "zh-TW") -> dict:
    return {
        "kind": "search_query",
        "url": None,
        "trust_level": "0.5",
        "language": language,
        "poll_interval_seconds": 43200,
        "config": {
            "query": query,
            "k": 5,
            "recency_days": 2,
            "section": section,
            "domains": domains,
        },
    }


ADDED: dict[str, dict] = {
    "NVIDIA Blog": {
        "kind": "rss",
        "url": "https://blogs.nvidia.com/feed/",
        "trust_level": "0.8",
        "language": "en",
        "poll_interval_seconds": 3600,
        "config": {"max_age_days": 7, "section": "ai"},
    },
    "搜尋：輝達": _search("輝達 NVIDIA 黃仁勳 財報 GPU 供應鏈", "ai", TW_NEWS),
    "搜尋：台積電：製程與產能": _search("台積電 先進製程 CoWoS 產能 2奈米", "tw", TW_NEWS),
    "搜尋：AI 伺服器供應鏈": _search("AI 伺服器 鴻海 廣達 緯創 緯穎 出貨", "tw", TW_NEWS),
    "搜尋：HBM 記憶體": _search(
        "HBM high bandwidth memory SK hynix Micron Samsung AI demand",
        "ai",
        ["reuters.com", "cnbc.com", "tomshardware.com", "theregister.com"],
        "en",
    ),
    "搜尋：AI 資料中心：電力與散熱": _search("AI 資料中心 電力 散熱 液冷", "ai", TW_NEWS),
}

PAUSED = [
    "CoinDesk",
    "搜尋：Trump OGE 278-T periodic transaction report stocks bonds",
    "搜尋：Pelosi periodic transaction report stock trades disclosure",
    "搜尋：機構觀點（貝萊德、先鋒、富達、瑞銀、道富）",
    "搜尋：機構觀點（摩根大通、高盛、資本集團、Amundi、紐約梅隆）",
    "搜尋：黃金",
    "搜尋：原物料：金屬",
    "搜尋：原物料：AI 資料中心帶動的金屬需求",
    "搜尋：原物料：能源",
    "搜尋：原物料：農產品",
    "搜尋：外匯：新台幣與美元",
    "搜尋：外匯：亞洲主要貨幣",
    "搜尋：外匯：歐美與大洋洲貨幣",
    "搜尋：外匯：東南亞貨幣",
]
CRYPTO_SEARCH = "搜尋：比特幣 以太幣 ETF 監管"


def _company_id(conn) -> object | None:
    return conn.execute(sa.text("SELECT id FROM companies WHERE slug = :s"), {"s": SLUG}).scalar()


def upgrade() -> None:
    conn = op.get_bind()
    company = _company_id(conn)
    if company is None:
        return
    conn.execute(
        sa.text("UPDATE companies SET mission = :m WHERE id = :c"), {"m": MISSION, "c": company}
    )
    conn.execute(
        sa.text(
            "INSERT INTO company_policies (id, company_id, key, value, updated_by)"
            " VALUES (gen_random_uuid(), :c, 'newsroom.topic_mix', CAST(:v AS jsonb),"
            " CAST(:a AS jsonb)) ON CONFLICT (company_id, key) DO NOTHING"
        ),
        {"c": company, "v": json.dumps(TOPIC_MIX, ensure_ascii=False), "a": json.dumps(ACTOR)},
    )
    conn.execute(
        sa.text(
            "UPDATE sources SET status = 'paused' WHERE company_id = :c AND name = ANY(:names)"
        ),
        {"c": company, "names": PAUSED},
    )
    conn.execute(
        sa.text(
            "UPDATE sources SET poll_interval_seconds = 86400 WHERE company_id = :c AND name = :n"
        ),
        {"c": company, "n": CRYPTO_SEARCH},
    )
    for name, spec in ADDED.items():
        conn.execute(
            sa.text(
                "INSERT INTO sources (id, company_id, name, kind, url, config, trust_level,"
                " language, poll_interval_seconds) VALUES (gen_random_uuid(), :c, :n, :k, :u,"
                " CAST(:cfg AS jsonb), CAST(:t AS numeric), :l, :p)"
                " ON CONFLICT (company_id, name) DO UPDATE SET status = 'active'"
            ),
            {
                "c": company,
                "n": name,
                "k": spec["kind"],
                "u": spec["url"],
                "cfg": json.dumps(spec["config"], ensure_ascii=False),
                "t": spec["trust_level"],
                "l": spec["language"],
                "p": spec["poll_interval_seconds"],
            },
        )


def downgrade() -> None:
    conn = op.get_bind()
    company = _company_id(conn)
    if company is None:
        return
    conn.execute(
        sa.text("UPDATE companies SET mission = :m WHERE id = :c"),
        {"m": OLD_MISSION, "c": company},
    )
    conn.execute(
        sa.text(
            "DELETE FROM company_policies WHERE company_id = :c AND key = 'newsroom.topic_mix'"
        ),
        {"c": company},
    )
    conn.execute(
        sa.text(
            "UPDATE sources SET status = 'active' WHERE company_id = :c AND name = ANY(:names)"
        ),
        {"c": company, "names": PAUSED},
    )
    conn.execute(
        sa.text(
            "UPDATE sources SET status = 'paused' WHERE company_id = :c AND name = ANY(:names)"
        ),
        {"c": company, "names": list(ADDED)},
    )
    conn.execute(
        sa.text(
            "UPDATE sources SET poll_interval_seconds = 43200 WHERE company_id = :c AND name = :n"
        ),
        {"c": company, "n": CRYPTO_SEARCH},
    )
