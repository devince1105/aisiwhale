"""Seed the e2e database with a few 13F filers' quarters (HD-11): 機構排行 and an institution's page
in a real browser. Prints ``{"period": ..., "previous": ...}``.

Twelve filers for the quarter the ranking shows (``ranked_period``, from today, so the test does
not age) and the one before: BlackRock first with its holdings worked out, T. Rowe Price filed in
thousands, the rest plain. Only ever the throwaway e2e database (``DATABASE_URL``).
"""

from __future__ import annotations

import asyncio
import json
import os
from datetime import UTC, date, datetime, timedelta

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from autora.domains.newsroom.models import InstitutionDetail, ThirteenFFiling
from autora.domains.newsroom.thirteenf_index import previous_period, ranked_period

NOW = datetime.now(UTC)
FILERS = [
    ("2012383", "BlackRock, Inc.", 6_729_538_649_155, 5_723_531_457_401, 1),
    ("80255", "PRICE T ROWE ASSOCIATES INC /MD/", 999_124_702, 864_926_000, 1000),
    ("93751", "STATE STREET CORP", 3_383_260_349_220, 2_896_359_015_000, 1),
    ("315066", "FMR LLC", 2_303_880_000_000, 1_898_436_000_000, 1),
    ("895421", "MORGAN STANLEY", 1_890_810_000_000, 1_660_000_000_000, 1),
    ("19617", "JPMORGAN CHASE & CO", 1_807_040_000_000, 1_557_000_000_000, 1),
    ("70858", "BANK OF AMERICA CORP /DE/", 1_552_070_000_000, 1_368_000_000_000, 1),
    ("914208", "Invesco Ltd.", 1_264_260_000_000, 1_023_000_000_000, 1),
    ("886982", "GOLDMAN SACHS GROUP INC", 1_151_630_000_000, 871_000_000_000, 1),
    ("1374170", "NORGES BANK", 1_003_230_000_000, 864_000_000_000, 1),
    ("1423053", "CITADEL ADVISORS LLC", 875_010_000_000, 618_000_000_000, 1),
    ("73124", "NORTHERN TRUST CORP", 859_790_000_000, 756_000_000_000, 1),
]


def filing(cik: str, name: str, period: date, value: int, scale: int, n: int) -> ThirteenFFiling:
    return ThirteenFFiling(
        accession=f"{int(cik):010d}-26-{n:06d}",
        cik=cik,
        company=name,
        form="13F-HR",
        filed=period + timedelta(days=40),
        period=period,
        manager=name,
        report_type="13F HOLDINGS REPORT",
        entries=4000,
        value_usd=value,
        read_at=NOW,
        attempts=0,
        scale=scale,
        scale_attempts=0,
    )


def blackrock(period: date, before: date) -> InstitutionDetail:
    top = [
        {
            "cusip": f"E2E{i:06d}",
            "name": f"E2E HOLDING {i + 1}",
            "title_of_class": "COM",
            "change": "increased",
            "shares": 2_000_000,
            "previous_shares": 1_000_000,
            "value_usd": 100_000_000_000 - i * 1_000_000_000,
            "previous_value_usd": 50_000_000_000,
            "weight_pct": 1.5,
            "traded_usd": 1_000_000_000,
            "split": None,
        }
        for i in range(12)
    ]
    return InstitutionDetail(
        cik="2012383",
        period=period,
        status="ready",
        computed_at=NOW,
        accessions=["0002012383-26-000001"],
        previous_period=before,
        stock_value_usd=6_706_500_000_000,
        previous_stock_value_usd=5_695_000_000_000,
        stocks=5455,
        net_bought_usd=125_600_000_000,
        counts={"new": 280, "increased": 3437, "decreased": 1254, "sold_out": 238},
        top=top,
        bought=top[:3],
        sold=[{**top[5], "change": "sold_out", "shares": 0, "traded_usd": -2_000_000_000}],
    )


async def main() -> None:
    period = ranked_period(date.today())
    before = previous_period(period)
    engine = create_async_engine(os.environ["DATABASE_URL"])
    async with async_sessionmaker(engine)() as session:
        for cik, name, now_value, before_value, scale in FILERS:
            session.add(filing(cik, name, period, now_value, scale, 1))
            session.add(filing(cik, name, before, before_value, scale, 2))
        session.add(blackrock(period, before))
        await session.commit()
    await engine.dispose()
    print(json.dumps({"period": period.isoformat(), "previous": before.isoformat()}))


if __name__ == "__main__":
    asyncio.run(main())
