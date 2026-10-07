"""P3-C-3: migration 0077 writes the ``coins.reconcile`` schedule once, and takes it away again.

On a database of its own, built from nothing, and named by revision (0076 ↔ 0077), never
``head``: later migrations are not this test's business.
"""

import os
import subprocess
import sys

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url

from autora.db.session import build_engine
from tests.conftest import PACKAGE_ROOT, _ensure_database


def _alembic(url: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=PACKAGE_ROOT,
        capture_output=True,
        text=True,
        env={**os.environ, "DATABASE_URL": url},
    )


@pytest.fixture
async def scratch(db_settings, db_engine):
    url = make_url(db_settings.database_url)
    name = f"{url.database}_coin_schedule"
    admin = url.set(database="postgres").render_as_string(hide_password=False)
    engine = build_engine(admin)
    async with engine.connect() as conn:
        await conn.execution_options(isolation_level="AUTOCOMMIT")
        await conn.execute(text(f'DROP DATABASE IF EXISTS "{name}"'))
    await _ensure_database(admin, name)
    try:
        yield url.set(database=name).render_as_string(hide_password=False)
    finally:
        async with engine.connect() as conn:
            await conn.execution_options(isolation_level="AUTOCOMMIT")
            await conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        await engine.dispose()


async def _rows(url: str, sql: str):
    engine = build_engine(url)
    try:
        async with engine.begin() as conn:
            return (await conn.execute(text(sql))).all()
    finally:
        await engine.dispose()


SCHEDULES = (
    "SELECT s.company_id, s.cron, s.timezone, s.handler, s.enabled, c.slug"
    " FROM schedules s JOIN companies c ON c.id = s.company_id WHERE s.name = 'coins.reconcile'"
)


async def test_0077_writes_the_schedule_for_the_oldest_company_once(scratch):
    assert _alembic(scratch, "upgrade", "0076").returncode == 0
    await _rows(
        scratch,
        "INSERT INTO companies (id, slug, name, created_at) VALUES"
        " (gen_random_uuid(), 'first', 'First', now() - interval '1 day'),"
        " (gen_random_uuid(), 'second', 'Second', now()) RETURNING id",
    )

    up = _alembic(scratch, "upgrade", "0077")
    assert up.returncode == 0, up.stderr
    ((_, cron, zone, handler, enabled, slug),) = await _rows(scratch, SCHEDULES)
    assert (cron, zone, handler, enabled, slug) == (
        "5 18 * * *",
        "Asia/Taipei",
        "coins.reconcile",
        True,
        "first",
    )

    down = _alembic(scratch, "downgrade", "0076")
    assert down.returncode == 0, down.stderr
    assert await _rows(scratch, SCHEDULES) == []

    again = _alembic(scratch, "upgrade", "0077")
    assert again.returncode == 0, again.stderr
    assert len(await _rows(scratch, SCHEDULES)) == 1


async def test_0077_on_a_database_with_no_company_writes_nothing(scratch):
    up = _alembic(scratch, "upgrade", "0077")
    assert up.returncode == 0, up.stderr
    assert await _rows(scratch, "SELECT 1 FROM schedules WHERE name = 'coins.reconcile'") == []
    assert (await _rows(scratch, "SELECT version_num FROM alembic_version"))[0][0] == "0077"
