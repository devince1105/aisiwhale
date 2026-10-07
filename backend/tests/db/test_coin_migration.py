"""P3-A: migration 0072 goes up, down and up again — and will not go down over coins that moved.

On a database of its own (``<test db>_coins_migration``), built from nothing, so the suite's
shared test database is never downgraded under the other tests. Every step names 0072 and 0071
rather than ``head``: later migrations (0073 onwards) are not this test's business.
"""

import os
import subprocess
import sys
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker

from autora.accounts import Reader
from autora.accounts.coins import TxnKind, grant
from autora.db.session import build_engine
from autora.runtime.actor import Actor
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
    name = f"{url.database}_coins_migration"
    admin = url.set(database="postgres").render_as_string(hide_password=False)
    engine = build_engine(admin)
    async with engine.connect() as conn:
        await conn.execution_options(isolation_level="AUTOCOMMIT")
        await conn.execute(text(f'DROP DATABASE IF EXISTS "{name}"'))
    await _ensure_database(admin, name)
    scratch_url = url.set(database=name).render_as_string(hide_password=False)
    try:
        yield scratch_url
    finally:
        async with engine.connect() as conn:
            await conn.execution_options(isolation_level="AUTOCOMMIT")
            await conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        await engine.dispose()


async def _scalar(url: str, sql: str):
    engine = build_engine(url)
    try:
        async with engine.begin() as conn:
            return (await conn.execute(text(sql))).scalar()
    finally:
        await engine.dispose()


async def test_0072_goes_up_down_and_up_again_and_keeps_moved_coins(scratch):
    version = "SELECT version_num FROM alembic_version"
    up = _alembic(scratch, "upgrade", "0072")
    assert up.returncode == 0, up.stderr
    assert await _scalar(scratch, version) == "0072"
    assert (
        await _scalar(scratch, "SELECT count(*) FROM coin_accounts WHERE owner_type = 'system'")
        == 3
    )

    down = _alembic(scratch, "downgrade", "0071")
    assert down.returncode == 0, down.stderr
    assert await _scalar(scratch, version) == "0071"
    assert await _scalar(scratch, "SELECT to_regclass('public.coin_txns')") is None
    assert (
        await _scalar(scratch, "SELECT count(*) FROM pg_proc WHERE proname LIKE 'autora_coin_%'")
        == 0
    )
    assert (
        await _scalar(
            scratch, "SELECT count(*) FROM pg_proc WHERE proname = 'autora_forbid_mutation'"
        )
        == 1
    )

    again = _alembic(scratch, "upgrade", "0072")
    assert again.returncode == 0, again.stderr
    assert await _scalar(scratch, version) == "0072"
    assert await _scalar(scratch, "SELECT count(*) FROM coin_accounts") == 3

    # a coin moves; then going back must refuse, and leave the ledger as it was
    engine = build_engine(scratch)
    try:
        async with async_sessionmaker(engine)() as session:
            reader = Reader(email=f"m{uuid.uuid4().hex[:10]}@example.com")
            session.add(reader)
            await session.flush()
            await grant(
                session, reader.id, requested=50, cap=100, kind=TxnKind.MONTHLY_GRANT,
                idempotency_key=f"grant:free:{reader.id}:2026-10", actor=Actor.system("test"),
            )  # fmt: skip
            await session.commit()
    finally:
        await engine.dispose()

    refused = _alembic(scratch, "downgrade", "0071")
    assert refused.returncode != 0
    assert "refusing to drop the ledger" in refused.stderr
    assert await _scalar(scratch, "SELECT version_num FROM alembic_version") == "0072"
    assert await _scalar(scratch, "SELECT count(*) FROM coin_txns") == 1
