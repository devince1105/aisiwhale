"""D-253: migration 0083 turns 艾矽鯨 to NVIDIA, TSMC and AI — and back — and leaves a database
without it alone. On a database of its own, built from nothing; every step names 0083 and 0082."""

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url

from autora.db.session import build_engine
from tests.conftest import _ensure_database
from tests.db.test_coin_migration import _alembic, _scalar


@pytest.fixture
async def scratch(db_settings, db_engine):
    url = make_url(db_settings.database_url)
    name = f"{url.database}_ai_focus_migration"
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


async def _run(url: str, *statements: str, **params) -> None:
    engine = build_engine(url)
    try:
        async with engine.begin() as conn:
            for statement in statements:
                await conn.execute(text(statement), params)
    finally:
        await engine.dispose()


CRYPTO = '{"section": "crypto"}'


async def test_0083_up_and_down_for_aisiwhale_only(scratch):
    assert (up := _alembic(scratch, "upgrade", "0082")).returncode == 0, up.stderr
    company, other = uuid.uuid4(), uuid.uuid4()
    add = (
        "INSERT INTO sources (id, company_id, name, kind, url, config, poll_interval_seconds)"
        " VALUES (gen_random_uuid(), :company, :name, :kind, :feed, CAST(:config AS jsonb), :every)"
    )
    await _run(
        scratch,
        "INSERT INTO companies (id, slug, name, mission) VALUES (:c, 'aisiwhale', '艾矽鯨', 'old')",
        "INSERT INTO companies (id, slug, name, mission) VALUES (:o, 'someone', 'x', 'theirs')",
        c=company, o=other,
    )  # fmt: skip
    for owner, name, kind, every in (
        (company, "CoinDesk", "rss", 3600),
        (company, "搜尋：比特幣 以太幣 ETF 監管", "search_query", 43200),
        (other, "CoinDesk", "rss", 3600),
    ):
        url = "https://www.coindesk.com/arc/outboundfeeds/rss/" if kind == "rss" else None
        await _run(
            scratch, add, company=owner, name=name, kind=kind, feed=url, config=CRYPTO, every=every
        )

    async def mission(who):
        return await _scalar(scratch, f"SELECT mission FROM companies WHERE id = '{who}'")

    async def source(who, name, column="status"):
        return await _scalar(
            scratch, f"SELECT {column} FROM sources WHERE company_id = '{who}' AND name = '{name}'"
        )

    async def count(table, who):
        return await _scalar(scratch, f"SELECT count(*) FROM {table} WHERE company_id = '{who}'")

    assert (up := _alembic(scratch, "upgrade", "0083")).returncode == 0, up.stderr
    assert "聚焦輝達" in await mission(company)
    assert await mission(other) == "theirs"
    assert await count("company_policies", company) == 1
    assert await source(company, "CoinDesk") == "paused"
    assert await source(other, "CoinDesk") == "active", "another company's sources are its own"
    assert await source(company, "搜尋：比特幣 以太幣 ETF 監管", "poll_interval_seconds") == 86400
    assert await count("sources", company) == 8  # its two, and the focus's six
    assert await source(company, "NVIDIA Blog") == "active"

    assert (down := _alembic(scratch, "downgrade", "0082")).returncode == 0, down.stderr
    assert "加密貨幣的監管、ETF 與市場動態" in await mission(company)
    assert await count("company_policies", company) == 0
    assert await source(company, "CoinDesk") == "active"
    assert await source(company, "NVIDIA Blog") == "paused", "kept: a source with items cannot go"
    assert (up := _alembic(scratch, "upgrade", "0083")).returncode == 0, up.stderr
    assert await source(company, "NVIDIA Blog") == "active", "up again: on again"
