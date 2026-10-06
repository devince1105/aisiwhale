"""Prepare the database for the browser end-to-end tests (T-315, frontend/web/e2e).

    .venv/bin/python backend/scripts/e2e_prepare.py

Uses ``<dev database>_e2e`` (never the dev database): creates it if missing, empties it, applies
the migrations, seeds the echo company (``seed_echo.py``) and the demo newsroom with its stories
(``seed_newsroom.py --gather``), makes the back office's admin account when
``E2E_ADMIN_EMAIL`` and ``E2E_ADMIN_PASSWORD`` are set (D-230: the browser signs in with a
password and keeps a cookie; no token in browser storage), and prints one JSON line:
``{"database_url": ..., "company_id": ..., "project_id": ..., "newsroom_company_id": ...,
"newsroom_project_id": ...}``.
The browser tests then start their own API and worker against that database.
"""

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession

from autora.db.session import build_engine
from autora.infra.settings import load_settings

BACKEND = Path(__file__).resolve().parents[1]


async def _reset(admin_url: str, url: str, name: str) -> None:
    admin = build_engine(admin_url)
    try:
        async with admin.connect() as conn:
            await conn.execution_options(isolation_level="AUTOCOMMIT")
            exists = await conn.scalar(
                text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": name}
            )
            if not exists:
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


async def _admin(url: str, email: str, password: str) -> None:
    """An admin as the site makes one: registered, then the address proven (D-230)."""
    from datetime import UTC, datetime

    from autora.accounts import credentials

    engine = build_engine(url)
    try:
        async with engine.begin() as conn:
            session = AsyncSession(bind=conn)
            outcome = await credentials.register(session, email, password)
            await credentials.verify_email(session, outcome.verify_token, now=datetime.now(UTC))
            await session.flush()
    finally:
        await engine.dispose()


def main() -> None:
    base = make_url(load_settings().database_url)
    name = f"{base.database}_e2e"
    url = base.set(database=name).render_as_string(hide_password=False)
    admin_url = base.set(database="postgres").render_as_string(hide_password=False)
    asyncio.run(_reset(admin_url, url, name))

    env = {**os.environ, "DATABASE_URL": url, "MODEL_PROVIDER": "fake"}
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND,
        env=env,
        check=True,
        capture_output=True,
    )
    seeded = subprocess.run(
        [sys.executable, str(BACKEND / "scripts" / "seed_echo.py")],
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    company = json.loads(seeded.stdout)
    # the demo newsroom (T-520): its sources read and clustered into stories, none started
    newsroom = json.loads(
        subprocess.run(
            [sys.executable, str(BACKEND / "scripts" / "seed_newsroom.py"), "--gather"],
            env=env | {"TOOLS_PROFILE": "fixture", "EMBED_PROVIDER": "fake"},
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    )
    admin_email, admin_password = (
        os.environ.get("E2E_ADMIN_EMAIL"),
        os.environ.get("E2E_ADMIN_PASSWORD"),
    )
    if admin_email and admin_password:
        asyncio.run(_admin(url, admin_email, admin_password))
    print(
        json.dumps(
            {
                "database_url": url,
                "company_id": company["company_id"],
                "project_id": company["project_id"],
                "newsroom_company_id": newsroom["company_id"],
                "newsroom_project_id": newsroom["project_id"],
            }
        )
    )


if __name__ == "__main__":
    main()
