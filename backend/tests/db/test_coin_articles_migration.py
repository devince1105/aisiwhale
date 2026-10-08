"""P4 (D-249): migration 0082 goes up, down and up again; the database holds COIN articles to
their price and unlocks to what was paid; and going back refuses while either is in use.

On a database of its own (``<test db>_coin_articles_migration``), built from nothing. Every step
names 0082 and 0081 rather than ``head``.
"""

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker

from autora.accounts.coins import TxnKind, grant, unlock_article
from autora.db.session import build_engine
from autora.runtime.actor import Actor
from tests.conftest import _ensure_database
from tests.db.test_coin_migration import _alembic, _scalar


@pytest.fixture
async def scratch(db_settings, db_engine):
    url = make_url(db_settings.database_url)
    name = f"{url.database}_coin_articles_migration"
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


async def _run(url: str, *statements: str, **params):
    engine = build_engine(url)
    try:
        async with engine.begin() as conn:
            for statement in statements:
                await conn.execute(text(statement), params)
    finally:
        await engine.dispose()


async def _an_article(url: str) -> uuid.UUID:
    company, story, article = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    await _run(
        url,
        "INSERT INTO companies (id, slug, name) VALUES (:c, :cs, 'p4')",
        "INSERT INTO stories (id, company_id, title, state) VALUES (:s, :c, 't', 'SELECTED')",
        "INSERT INTO articles (id, company_id, story_id, slug, title, primary_lang)"
        " VALUES (:a, :c, :s, :as, 't', 'zh-TW')",
        c=company, cs=f"p4-{company.hex[:8]}", s=story, a=article, **{"as": f"a-{article.hex[:8]}"},
    )  # fmt: skip
    return article


async def test_0082_goes_up_down_and_up_again_and_guards_prices_and_unlocks(scratch):
    version = "SELECT version_num FROM alembic_version"
    assert (up := _alembic(scratch, "upgrade", "0082")).returncode == 0, up.stderr
    assert await _scalar(scratch, version) == "0082"
    assert (down := _alembic(scratch, "downgrade", "0081")).returncode == 0, down.stderr
    assert await _scalar(scratch, "SELECT to_regclass('public.article_unlocks')") is None
    assert (
        await _scalar(
            scratch,
            "SELECT count(*) FROM information_schema.columns"
            " WHERE table_name = 'articles' AND column_name = 'coin_price'",
        )
        == 0
    )
    assert (again := _alembic(scratch, "upgrade", "0082")).returncode == 0, again.stderr

    article = await _an_article(scratch)
    for bad in (
        "UPDATE articles SET access = 'coin' WHERE id = :a",  # COIN without a price
        "UPDATE articles SET access = 'coin', coin_price = 0 WHERE id = :a",
        "UPDATE articles SET access = 'coin', coin_price = 101 WHERE id = :a",
        "UPDATE articles SET coin_price = 5 WHERE id = :a",  # a price on a free article
        "UPDATE articles SET access = 'gold' WHERE id = :a",
    ):
        with pytest.raises(IntegrityError):
            await _run(scratch, bad, a=article)
    await _run(
        scratch, "UPDATE articles SET access = 'coin', coin_price = 100 WHERE id = :a", a=article
    )

    refused = _alembic(scratch, "downgrade", "0081")
    assert refused.returncode != 0 and "articles are COIN" in refused.stderr
    assert await _scalar(scratch, version) == "0082"

    # an unlock, paid for by a spend; never changed, and going back refuses over it
    reader = uuid.uuid4()
    await _run(
        scratch, "INSERT INTO readers (id, email) VALUES (:r, :e)",
        r=reader, e=f"u{reader.hex[:10]}@example.com",
    )  # fmt: skip
    engine = build_engine(scratch)
    try:
        async with async_sessionmaker(engine)() as session:
            await grant(
                session, reader, requested=100, cap=100, kind=TxnKind.PROMOTION_GRANT,
                idempotency_key=f"promo:m:{reader}", actor=Actor.system("test"),
            )  # fmt: skip
            done = await unlock_article(
                session, reader, article, price=100, actor=Actor.human(f"reader:{reader}")
            )
            txn = done.unlock.coin_txn_id
            await session.commit()
    finally:
        await engine.dispose()
    with pytest.raises(DBAPIError):
        await _run(scratch, "UPDATE article_unlocks SET price_paid = 1")
    with pytest.raises(DBAPIError):
        await _run(scratch, "DELETE FROM article_unlocks")
    with pytest.raises(IntegrityError):  # one per reader and article
        await _run(
            scratch,
            "INSERT INTO article_unlocks (id, reader_id, article_id, coin_txn_id, price_paid)"
            " VALUES (:i, :r, :a, :t, 1)",
            i=uuid.uuid4(), r=reader, a=article, t=txn,
        )  # fmt: skip

    await _run(
        scratch, "UPDATE articles SET access = 'free', coin_price = NULL WHERE id = :a", a=article
    )
    refused = _alembic(scratch, "downgrade", "0081")
    assert refused.returncode != 0 and "readers have paid for articles" in refused.stderr
    assert await _scalar(scratch, "SELECT count(*) FROM article_unlocks") == 1
