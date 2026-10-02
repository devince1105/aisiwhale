"""Write the public site's demo office script (D-155) from one real daily cycle.

    .venv/bin/python backend/scripts/demo_office_script.py \
        --company 01a0d2c7-c737-771a-936d-11778f88f309 \
        --from 2026-10-01T06:00Z --to 2026-10-01T07:30Z

The public page /news/<lang>/office replays it in the browser: the 3D office, driven by events the
way the back office is, but by a script instead of the stream. The cycle's rhythm is real — who
picks up what, when, in what order, the revision rounds — and everything else is not:

- the eight people are made up (``CAST``), none of them the company's own staff;
- every id is a fresh one (uuid5 of the original), the company included;
- payloads keep only what the office draws (``KEEP``); titles, summaries, claims, sources, tool
  arguments, URLs and costs are dropped or replaced with neutral demo text;
- the timing is squeezed into a loop of a few minutes.

Output: frontend/web/src/features/demo-office/script.json. Its test checks every event against
the event schema and that nothing of the real cycle leaks through.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import text

from autora.db.session import build_engine
from autora.infra.settings import load_settings

OUT = Path(__file__).resolve().parents[2] / "frontend/web/src/features/demo-office/script.json"
NS = uuid.UUID("6f1e3c52-1d4b-4b8e-9a51-5d0e7c2a9b10")
COMPANY = str(uuid.uuid5(NS, "demo:company"))

LOOP_MS = 210_000
TAIL_MS = 8_000
MAX_GAP_MS = 2_000
MIN_GAP_MS = 120
SAME_AGENT_GAP_MS = 400
MAX_DISPLAY_MS = 6_000

# (role, name, avatar_key, department_key, office_zone_key, business_unit_key)
CAST = [
    ("ceo", "Rinka Tsukishiro｜月城凜花", "demo_rinka", "executive", "ceo", None),
    (
        "editor_in_chief",
        "Kaede Shirasagi｜白鷺楓",
        "demo_kaede",
        "newsroom",
        "editorial",
        "ai_media",
    ),
    (
        "news_intelligence",
        "Nanami Amagiri｜天霧七海",
        "demo_nanami",
        "newsroom_research",
        "research",
        "ai_media",
    ),
    (
        "researcher",
        "Shiori Fumino｜文野栞",
        "demo_shiori",
        "newsroom_research",
        "research",
        "ai_media",
    ),
    (
        "analyst",
        "Yuzuha Kazuki｜數木柚葉",
        "demo_yuzuha",
        "newsroom_research",
        "research",
        "ai_media",
    ),
    (
        "writer",
        "Kotone Sumino｜墨野琴音",
        "demo_kotone",
        "newsroom_writing",
        "editorial",
        "ai_media",
    ),
    ("editor", "Mio Akemura｜朱村澪", "demo_mio", "newsroom_editing", "editorial", "ai_media"),
    (
        "marketing",
        "Ririka Tomoshibi｜燈火莉莉花",
        "demo_ririka",
        "newsroom_audience",
        "growth",
        "ai_media",
    ),
]

DEPARTMENT_NAMES = {
    "zh-TW": {
        "executive": "決策層",
        "newsroom": "編輯部",
        "newsroom_research": "研究組",
        "newsroom_writing": "撰稿組",
        "newsroom_editing": "審稿組",
        "newsroom_audience": "推廣組",
    },
    "en": {
        "executive": "Executive",
        "newsroom": "Newsroom",
        "newsroom_research": "Research",
        "newsroom_writing": "Writing",
        "newsroom_editing": "Editing",
        "newsroom_audience": "Audience",
    },
}

# What the office draws, per event type; every other payload field is dropped. Types not listed
# are not replayed at all: tool calls carry their arguments, claims and evidence carry the real
# reporting, schedules and budgets are noise to a visitor.
KEEP: dict[str, tuple[str, ...]] = {
    "CYCLE_STARTED": ("seq", "stage"),
    "CYCLE_STAGE_CHANGED": ("from_stage", "to_stage"),
    "WORKFLOW_RUN_CREATED": ("template", "task_ids"),
    "WORKFLOW_RUN_COMPLETED": ("duration_ms",),
    "TASK_CREATED": ("name", "required_role", "depends_on", "workflow_run_id"),
    "TASK_READY": ("required_role",),
    "TASK_STARTED": ("run_id", "agent_id", "attempt"),
    "TASK_WAITING": ("reason", "approval_id"),
    "TASK_SUCCEEDED": ("run_id", "unlocks"),
    "AGENT_RUN_STARTED": ("attempt", "task_name", "required_role"),
    "AGENT_THINKING": ("phase", "step_seq"),
    "AGENT_WORKING": ("tool", "step_seq", "progress"),
    "AGENT_REVIEWING": ("phase", "attempt", "issues_count"),
    "AGENT_WAITING": ("reason", "approval_id", "blocked_task_id", "waiting_on_roles"),
    "AGENT_RUN_COMPLETED": ("steps", "duration_ms", "handoff"),
    "APPROVAL_REQUESTED": ("kind", "ref_type"),
    "ARTICLE_REVIEWED": ("by_role", "verdict", "fact_check_passed"),
    "ARTICLE_REVISION_REQUESTED": ("back_to", "by_role", "revision", "issues_count"),
}

FIXED_TASKS = {
    ("plan", "ceo"): "規劃今日方針",
    ("brief", "news_intelligence"): "市場晨報",
    ("plan", "editor_in_chief"): "安排今日版面",
}
DONE = {
    "plan": "訂好今日目標",
    "brief": "整理好今日市場重點",
    "research": "蒐集並核對了示範資料",
    "analysis": "整理出報導角度",
    "draft": "完成一版示範稿件",
    "cover": "選好首圖",
    "review": "審完稿件",
    "chief_review": "終審完成",
    "distribute": "排好推廣",
}
ROUND = re.compile(r"（第 \d+ 輪）$")

ID_FIELDS = ("aggregate_id", "agent_id", "task_id", "run_id", "workflow_run_id", "cycle_id")


def demo_id(original: str | None) -> str | None:
    return None if original is None else str(uuid.uuid5(NS, f"demo:{original}"))


def agent_id(role: str) -> str:
    return str(uuid.uuid5(NS, f"demo:agent:{role}"))


async def load(company: str, start: str, end: str) -> tuple[list[dict[str, Any]], dict[str, str]]:
    engine = build_engine(load_settings().database_url)
    try:
        async with engine.connect() as conn:
            rows = (
                (
                    await conn.execute(
                        text(
                            "select event_type, aggregate_type, aggregate_id::text, agent_id::text,"
                            " task_id::text, run_id::text, workflow_run_id::text, cycle_id::text,"
                            " actor, payload, occurred_at from events"
                            " where company_id = :company and occurred_at between :start and :end"
                            " order by seq"
                        ),
                        {
                            "company": company,
                            "start": datetime.fromisoformat(start),
                            "end": datetime.fromisoformat(end),
                        },
                    )
                )
                .mappings()
                .all()
            )
            roles = (
                await conn.execute(
                    text("select id::text, role from agents where company_id = :company"),
                    {"company": company},
                )
            ).all()
    finally:
        await engine.dispose()
    return [dict(r) for r in rows], {agent: role for agent, role in roles}


def build(rows: list[dict[str, Any]], roles: dict[str, str]) -> dict[str, Any]:
    real_agent = {agent: agent_id(role) for agent, role in roles.items()}

    def remap(value: str | None) -> str | None:
        if value is None:
            return None
        return real_agent.get(value) or demo_id(value)

    # task id -> (name, display name in the demo); the stories become 示範報導 A, B, C
    stories: dict[str, str] = {}
    tasks: dict[str, tuple[str, str]] = {}
    for row in rows:
        if row["event_type"] != "TASK_CREATED":
            continue
        p = row["payload"]
        fixed = FIXED_TASKS.get((p["name"], p["required_role"]))
        if fixed:
            shown = fixed
        else:
            prefix, _, rest = p["display_name"].partition("：")
            story = ROUND.sub("", rest)
            label = stories.setdefault(story, f"示範報導 {chr(ord('A') + len(stories))}")
            again = ROUND.search(rest)
            shown = f"{prefix}：{label}{again.group(0) if again else ''}"
        tasks[row["aggregate_id"]] = (p["name"], shown)

    events: list[dict[str, Any]] = []
    for row in rows:
        kind = row["event_type"]
        if kind not in KEEP:
            continue
        p = row["payload"]
        payload: dict[str, Any] = {k: p[k] for k in KEEP[kind] if k in p}
        for key in ("run_id", "agent_id", "approval_id", "blocked_task_id", "workflow_run_id"):
            if payload.get(key):
                payload[key] = remap(payload[key])
        if "depends_on" in payload:
            payload["depends_on"] = [remap(t) for t in payload["depends_on"]]
        if "task_ids" in payload:
            payload["task_ids"] = [remap(t) for t in payload["task_ids"]]
        for key in ("unlocks", "handoff"):
            if key in payload:
                payload[key] = [
                    {**item, "task_id": remap(item["task_id"])} for item in payload[key]
                ]
        name, shown = tasks.get(row["task_id"] or "", ("", "示範工作"))
        if kind == "CYCLE_STARTED" or kind == "CYCLE_STAGE_CHANGED":
            payload["deadline"] = None
        if kind == "WORKFLOW_RUN_CREATED":
            payload["params"] = {}
            payload["project_id"] = demo_id(p.get("project_id") or "project")
        if kind == "TASK_CREATED":
            payload["display_name"] = tasks[row["aggregate_id"]][1]
            payload["budget_usd"] = None
        if kind == "TASK_SUCCEEDED":
            payload["output_ref"] = None
        if kind == "AGENT_RUN_STARTED":
            payload["input_summary"] = None
        if kind == "AGENT_WORKING":
            payload["tool_call_id"] = f"c{len(events)}"
        if kind == "AGENT_RUN_COMPLETED":
            payload["output_summary"] = DONE.get(name, "完成工作")
            payload["cost_usd"] = "0"
        if kind == "APPROVAL_REQUESTED":
            payload["ref_id"] = demo_id(p.get("ref_id") or "approval")
            payload["summary"] = f"{shown} 等待人工核准" if row["task_id"] else "示範：等待人工核准"
            payload["expires_at"] = None
        if kind.startswith("ARTICLE_"):
            payload["article_id"] = demo_id(p["article_id"])
            payload["version_id"] = demo_id(p["version_id"])

        actor = row["actor"]
        event: dict[str, Any] = {
            "event_type": kind,
            "aggregate_type": row["aggregate_type"],
            **{f: remap(row[f]) for f in ID_FIELDS},
            "actor": {
                "kind": actor["kind"],
                "id": remap(actor["id"]) if actor["kind"] == "agent" else actor["id"],
            },
            "payload": payload,
            "_at": row["occurred_at"],
        }
        if kind == "AGENT_RUN_COMPLETED" and p.get("display_until"):
            until = datetime.fromisoformat(p["display_until"].replace("Z", "+00:00"))
            event["du"] = max(
                0, min(MAX_DISPLAY_MS, int((until - row["occurred_at"]).total_seconds() * 1000))
            )
        events.append(event)

    # timing: real gaps, capped, a floor so one agent's states do not blur, then scaled to the loop
    gaps: list[float] = [0.0]
    for before, after in zip(events, events[1:], strict=False):
        gap = (after["_at"] - before["_at"]).total_seconds() * 1000
        floor = (
            SAME_AGENT_GAP_MS
            if after["agent_id"] and after["agent_id"] == before["agent_id"]
            else MIN_GAP_MS
        )
        gaps.append(max(floor, min(MAX_GAP_MS, gap)))
    scale = min(3.0, max(0.5, LOOP_MS / sum(gaps)))
    t = 0.0
    for event, gap in zip(events, gaps, strict=True):
        t += gap * scale
        event["t"] = round(t)
        event["event_id"] = str(
            uuid.uuid5(NS, f"demo:event:{len(events)}:{event['t']}:{event['event_type']}")
        )
        del event["_at"]

    return {
        "loop_ms": round(t) + TAIL_MS,
        "company_id": COMPANY,
        "department_names": DEPARTMENT_NAMES,
        "agents": [
            {
                "id": agent_id(role),
                "role": role,
                "display_name": name,
                "avatar_key": avatar,
                "department_id": str(uuid.uuid5(NS, f"demo:department:{department}")),
                "department_key": department,
                "office_zone_key": zone,
                "business_unit_key": unit,
            }
            for role, name, avatar, department, zone, unit in CAST
        ],
        "events": events,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--company", required=True)
    parser.add_argument("--from", dest="start", required=True)
    parser.add_argument("--to", dest="end", required=True)
    args = parser.parse_args()
    rows, roles = asyncio.run(load(args.company, args.start, args.end))
    script = build(rows, roles)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(script, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8"
    )
    size = OUT.stat().st_size // 1024
    loop = script["loop_ms"] / 1000
    print(f"{len(script['events'])} events, loop {loop:.0f} s, {size} KB -> {OUT}")


if __name__ == "__main__":
    main()
