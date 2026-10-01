"""Async engine and session factory.

Usage:

    async with session_scope() as session:
        ...  # commits on success, rolls back on error

The engine is created lazily from ``get_settings()`` and cached per process.
Workers and the API share this module; Alembic builds its own engine in env.py.
"""

from __future__ import annotations

import ssl
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import certifi
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from autora.infra.settings import Settings, get_settings

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


TLS_MODES = {"require", "verify-ca", "verify-full", "prefer", "allow", "true", "on"}


def connection_url(url: str) -> tuple[URL, dict[str, Any]]:
    """A libpq-style URL as asyncpg takes it (D-153): ``sslmode`` (Neon: ``require``) becomes a
    TLS connection that checks the server's certificate against certifi's roots — asyncpg's own
    ``require`` encrypts without checking — and ``channel_binding``, which asyncpg does not take,
    is dropped. A URL without either is left as it is (local Docker, tests)."""
    parsed = make_url(url)
    query = dict(parsed.query)
    mode = str(query.pop("sslmode", "") or query.pop("ssl", "") or "").lower()
    query.pop("channel_binding", None)
    connect_args: dict[str, Any] = {}
    if mode in TLS_MODES:
        connect_args["ssl"] = ssl.create_default_context(cafile=certifi.where())
    return parsed.set(query=query), connect_args


def build_engine(settings: Settings | str) -> AsyncEngine:
    """Engine from Settings, or from a raw URL (tests, admin tasks)."""
    raw = settings if isinstance(settings, str) else settings.database_url
    echo = False if isinstance(settings, str) else settings.db_echo
    url, connect_args = connection_url(raw)
    return create_async_engine(
        url,
        echo=echo,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=5,
        connect_args=connect_args,
    )


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = build_engine(get_settings())
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(get_engine(), expire_on_commit=False)
    return _sessionmaker


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """Transactional scope: commit on success, rollback on exception."""
    session = get_sessionmaker()()
    try:
        yield session
        await session.commit()
    except BaseException:
        await session.rollback()
        raise
    finally:
        await session.close()


async def dispose_engine() -> None:
    """Close pooled connections (call on process shutdown and between test sessions)."""
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _sessionmaker = None
