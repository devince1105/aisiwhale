"""Replay the newsroom's evaluation set (D-134): its latest analysed stories, drafted and reviewed
again in a database of their own.

    .venv/bin/python backend/scripts/newsroom_eval.py --simulated            # the fake model, free
    .venv/bin/python backend/scripts/newsroom_eval.py --stories 10 --yes     # the real model

Uses ``<dev database>_eval`` (never the dev database): empties it, applies the migrations, copies
the company's standing and the chosen stories with their claims and evidence, and runs draft →
review → the editor-in-chief's review for each with the production loops. Prints the set's
numbers and writes them, story by story, to ``data/evals/<label>-<time>.json``.

The real model costs money: ``--yes`` is required, and ``--max-usd`` (default 2) caps the run —
the cost guard stops calling the model once the run has spent it.
"""

import argparse
import asyncio
import json
import os
import subprocess
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker

from autora.app import build_runtime, build_worker
from autora.db.models import WorkflowRun
from autora.db.session import build_engine
from autora.domains.newsroom import models as _newsroom_models  # noqa: F401 (the tables)
from autora.domains.newsroom.evaluation import (
    EVAL_TEMPLATE,
    REPLAY,
    copy_cases,
    pick_cases,
    replay_analysis,
    result_for,
    summarize,
)
from autora.domains.newsroom.planning import _newsroom_project
from autora.infra.settings import load_settings

BACKEND = Path(__file__).resolve().parents[1]
DEFAULT_COMPANY = "01a0d2c7-c737-771a-936d-11778f88f309"


async def _reset(admin_url: str, url: str, name: str) -> None:
    admin = build_engine(admin_url)
    try:
        async with admin.connect() as conn:
            await conn.execution_options(isolation_level="AUTOCOMMIT")
            if not await conn.scalar(
                text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": name}
            ):
                await conn.execute(text(f'CREATE DATABASE "{name}"'))
    finally:
        await admin.dispose()
    engine = build_engine(url)
    try:
        async with engine.begin() as conn:
            await conn.execute(text("DROP SCHEMA public CASCADE"))
            await conn.execute(text("CREATE SCHEMA public"))
    finally:
        await engine.dispose()


async def run(args: argparse.Namespace) -> None:
    settings = load_settings()
    base = make_url(settings.database_url)
    name = f"{base.database}_eval"
    url = base.set(database=name).render_as_string(hide_password=False)
    admin_url = base.set(database="postgres").render_as_string(hide_password=False)
    company_id = uuid.UUID(args.company)

    source = build_engine(settings.database_url)
    try:
        async with async_sessionmaker(source)() as session:
            cases = await pick_cases(session, company_id, args.stories)
    finally:
        await source.dispose()
    if not cases:
        sys.exit("no analysed stories to replay")
    print(f"{len(cases)} stories, {'simulated model' if args.simulated else 'the real model'}")

    await _reset(admin_url, url, name)
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND,
        env={**os.environ, "DATABASE_URL": url},
        check=True,
        capture_output=True,
    )
    source, target = build_engine(settings.database_url), build_engine(url)
    try:
        async with source.connect() as src, target.begin() as dst:
            copied = await copy_cases(src, dst, company_id, cases)
        print("copied:", ", ".join(f"{k} {v}" for k, v in copied.items() if v))

        update = {"database_url": url, "model_daily_cap_usd": args.max_usd}
        if args.simulated:
            update["model_provider"] = "fake"
        local = settings.model_copy(update=update)
        runtime = build_runtime(local)
        runtime.workflows.templates.register(EVAL_TEMPLATE)
        runtime.services.register(REPLAY, replay_analysis)
        sessions = async_sessionmaker(target, expire_on_commit=False)
        runs: dict[uuid.UUID, object] = {}
        async with sessions() as session:
            project_id = await _newsroom_project(session, company_id)
            if project_id is None:
                sys.exit("the company has no active newsroom project to run in")
            for case in cases:
                run_row, _ = await runtime.workflows.instantiate(
                    session,
                    EVAL_TEMPLATE.name,
                    company_id=company_id,
                    project_id=project_id,
                    params={
                        "story_id": str(case.story_id),
                        "title": case.title,
                        "analysis": case.analysis,
                    },
                )
                runs[run_row.id] = case
            await session.commit()
        started = datetime.now(UTC)
        worker = build_worker(
            local, session_factory=sessions, company_ids=frozenset({company_id}), runtime=runtime
        )
        deadline = started.timestamp() + args.timeout_minutes * 60
        while True:
            await worker.run_until_idle(max_ticks=100_000)
            # idle can mean waiting: a failed attempt is retried after a pause (available_at)
            async with sessions() as session:
                waiting = await session.scalar(
                    text(
                        "select min(available_at) from tasks where state = 'READY' "
                        "and attempt < max_attempts and workflow_run_id = any(:runs)"
                    ),
                    {"runs": list(runs)},
                )
            if waiting is None or datetime.now(UTC).timestamp() > deadline:
                break
            await asyncio.sleep(
                max(1.0, min(30.0, (waiting - datetime.now(UTC)).total_seconds() + 0.5))
            )
        results = []
        async with sessions() as session:
            for run_id, case in runs.items():
                row = await session.scalar(select(WorkflowRun).where(WorkflowRun.id == run_id))
                results.append(await result_for(session, row, case))
    finally:
        await source.dispose()
        await target.dispose()

    summary = summarize(results)
    summary |= {
        "label": args.label,
        "model": "simulated" if args.simulated else local.model_provider,
        "started_at": started.isoformat(),
    }
    out = BACKEND.parent / "data" / "evals"
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{args.label}-{started:%Y%m%d-%H%M}.json"
    path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    shares = ("first_review_accepted", "accepted", "rejected", "failed_or_unfinished")
    print(" · ".join(f"{k.replace('_', ' ')} {summary[k]:.0%}" for k in shares))
    print(
        f"drafts/story {summary['drafts_per_story']:.1f}"
        f" · ${summary['cost_per_story_usd']:.4f}/story"
    )
    print("issues:", ", ".join(f"{k} {v}" for k, v in summary["issue_kinds"].items()) or "none")
    for r in summary["cases"]:
        print(
            f"  {r['ended']:<10} first={r['first_review']!s:<7} drafts={r['drafts']}"
            f" (production: {r['production']}) {r['title'][:50]}"
        )
    print(f"written to {path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--stories", type=int, default=10)
    parser.add_argument("--company", default=DEFAULT_COMPANY)
    parser.add_argument("--label", default="run")
    parser.add_argument("--simulated", action="store_true", help="the fake model: no cost")
    parser.add_argument("--yes", action="store_true", help="run the real model (costs money)")
    parser.add_argument("--max-usd", type=float, default=2.0)
    parser.add_argument("--timeout-minutes", type=float, default=60.0)
    args = parser.parse_args()
    if not args.simulated and not args.yes:
        sys.exit("the real model costs money: pass --yes (and --max-usd to cap it), or --simulated")
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
