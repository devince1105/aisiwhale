"""Which US ticker a 13F CUSIP is (HD-03, D-217): 13F filings name issuers and CUSIPs, never
tickers, and the holdings dashboard's simulated return needs prices, which need a ticker.

OpenFIGI (Bloomberg's open symbology, free) maps a CUSIP to every listing of the security; the US
composite one (``exchCode`` US) in the Equity sector is the ticker, written as the site writes it
(``BRK/B`` is ``BRK.B``). Two things were learned from the filers the site follows (2026-10-06,
the shares making up 90% of each one's latest 13F):

- a code beginning with a letter is a CINS — a company incorporated abroad (Linde ``G5495…``,
  ASML ``N0705…``): asked as a CUSIP, OpenFIGI finds nothing; asked as a CINS, it does;
- a company taken over since is no longer listed (Electronic Arts, Chart Industries): it is
  found only when unlisted equities are asked for too.

With both, 295 of 301 mapped. The six that did not are preferred shares and mandatory
convertibles (Bruker's, Super Micro's, Alphabet's): no common stock, so no ticker — and matching
them by issuer name would be wrong ("ALPHABET INC" is not GOOGL there), so nothing does.

Answers are kept (``cusip_symbols``): a ticker for good, a CUSIP without one asked again after
``RECHECK``. Nothing here is a model's: the mapping is a lookup, the choice a rule.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from autora.domains.newsroom.models import CusipSymbol, PortfolioPosition, PortfolioQuarter

log = logging.getLogger(__name__)

OPENFIGI = "https://api.openfigi.com/v3/mapping"
RECHECK = timedelta(days=30)
"""A CUSIP OpenFIGI had no US common stock for is asked again after this: one listed since."""
MAX_PER_RUN = 500
"""CUSIPs asked in one run: the first, with every kept quarter new, takes a few runs."""


class CusipError(Exception):
    """OpenFIGI could not be asked, or answered something else than one answer a CUSIP."""


@dataclass(frozen=True)
class Listing:
    """What OpenFIGI says a CUSIP is."""

    symbol: str | None
    """The US ticker, as the site writes it; None when there is no US common stock."""
    name: str | None
    security_type: str | None


def job(cusip: str) -> dict[str, Any]:
    """One CUSIP, as OpenFIGI's mapping takes it."""
    return {
        "idType": "ID_CINS" if cusip[:1].isalpha() else "ID_CUSIP",
        "idValue": cusip,
        "includeUnlistedEquities": True,
    }


def read(answer: dict[str, Any]) -> Listing:
    """One CUSIP's answer: its US composite listing in the Equity sector, if it has one. A CUSIP
    OpenFIGI does not know (``warning``) or calls malformed (``error``) has none."""
    rows = [row for row in answer.get("data") or [] if isinstance(row, dict)]
    us = next(
        (r for r in rows if r.get("exchCode") == "US" and r.get("marketSector") == "Equity"),
        None,
    )
    if us is None or not us.get("ticker"):
        first = rows[0] if rows else {}
        return Listing(None, first.get("name"), first.get("securityType"))
    return Listing(str(us["ticker"]).replace("/", "."), us.get("name"), us.get("securityType"))


PostJson = Callable[[str, list[dict[str, Any]]], Awaitable[list[dict[str, Any]]]]


class OpenFigi:
    def __init__(self, post: PostJson, *, keyed: bool, pause: float | None = None) -> None:
        self.post = post
        self.batch = 100 if keyed else 10
        """CUSIPs a request: 10 without a key, 100 with one."""
        self.pause = (0.3 if keyed else 2.5) if pause is None else pause
        """Between two requests: 25 a minute without a key, 25 in six seconds with one."""

    async def ask(self, cusips: list[str]) -> dict[str, Listing]:
        """One request's worth (``batch`` at most): each CUSIP's listing."""
        answers = await self.post(OPENFIGI, [job(c) for c in cusips])
        if not isinstance(answers, list) or len(answers) != len(cusips):
            raise CusipError(f"OpenFIGI answered {answers!r:.200} for {len(cusips)} CUSIPs")
        return {
            c: read(a if isinstance(a, dict) else {}) for c, a in zip(cusips, answers, strict=True)
        }


def http_post(api_key: str | None = None, timeout: float = 30.0) -> PostJson:
    import httpx

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["X-OPENFIGI-APIKEY"] = api_key

    async def post(url: str, body: list[dict[str, Any]]) -> list[dict[str, Any]]:
        try:
            async with httpx.AsyncClient(timeout=timeout, headers=headers) as client:
                return (await client.post(url, json=body)).raise_for_status().json()
        except (httpx.HTTPError, ValueError) as exc:
            raise CusipError(f"OpenFIGI: {exc}") from exc

    return post


async def map_cusips(
    session: AsyncSession,
    company_id: uuid.UUID,
    figi: OpenFigi,
    *,
    now: datetime | None = None,
    limit: int = MAX_PER_RUN,
) -> int:
    """The company's kept quarters' shares (not bonds: they have no ticker) whose CUSIP has no
    answer yet, or had none for ``RECHECK``, asked of OpenFIGI. The answers are everybody's — a
    CUSIP is the same security whoever holds it. Each request's are kept as they come, so a
    failure keeps what was asked before it. How many CUSIPs were asked."""
    now = now or datetime.now(UTC)
    answered = select(CusipSymbol.cusip).where(
        or_(CusipSymbol.symbol.is_not(None), CusipSymbol.checked_at > now - RECHECK)
    )
    # the largest holdings first: a filer of a thousand (Bridgewater) takes a few runs, and its
    # card's ring and moves should not wait for its smallest
    largest = func.max(PortfolioPosition.value_usd)
    todo = list(
        (
            await session.scalars(
                select(PortfolioPosition.cusip)
                .join(PortfolioQuarter, PortfolioQuarter.id == PortfolioPosition.quarter_id)
                .where(
                    PortfolioQuarter.company_id == company_id,
                    PortfolioPosition.kind == "SH",
                    PortfolioPosition.cusip.not_in(answered),
                )
                .group_by(PortfolioPosition.cusip)
                .order_by(largest.desc(), PortfolioPosition.cusip)
                .limit(limit)
            )
        ).all()
    )
    for start in range(0, len(todo), figi.batch):
        if start:
            await asyncio.sleep(figi.pause)
        found = await figi.ask(todo[start : start + figi.batch])
        statement = insert(CusipSymbol).values(
            [
                {
                    "cusip": cusip,
                    "symbol": listing.symbol,
                    "name": listing.name,
                    "security_type": listing.security_type,
                    "checked_at": now,
                }
                for cusip, listing in found.items()
            ]
        )
        await session.execute(
            statement.on_conflict_do_update(
                index_elements=["cusip"],
                set_={
                    name: statement.excluded[name]
                    for name in ("symbol", "name", "security_type", "checked_at")
                },
            )
        )
    if todo:
        log.info("cusips: %d asked of OpenFIGI", len(todo))
    return len(todo)


async def symbols(session: AsyncSession, cusips: list[str]) -> dict[str, str]:
    """The US ticker of each of ``cusips`` that has one."""
    if not cusips:
        return {}
    rows = await session.execute(
        select(CusipSymbol.cusip, CusipSymbol.symbol).where(
            CusipSymbol.cusip.in_(cusips), CusipSymbol.symbol.is_not(None)
        )
    )
    return {cusip: symbol for cusip, symbol in rows.all() if symbol}
