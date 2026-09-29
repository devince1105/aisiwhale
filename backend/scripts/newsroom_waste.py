"""How much of the newsroom's work goes nowhere, day by day (D-130).

    .venv/bin/python backend/scripts/newsroom_waste.py [--days 14] [--company <id>]

For each day (Asia/Taipei) the stories the desk drafted: how many were published, rejected or
are still open, drafts and reviews per story, how often the editor sent a draft back, and what
the agents spent on stories that ended rejected against those that were published. Read-only.

The baseline it was written against (2026-09-27, before D-083 and D-130): 18 stories, 12 of
them rejected, 3.2 drafts per story, 45 of 58 reviews sent back, and 72% of the day's spend
($0.90 of $1.25) on stories that ended rejected. A day after a change is only worth comparing on the
same measures, which is why they live here and not in a one-off query.
"""

import argparse
import asyncio

from sqlalchemy import text

from autora.db.session import build_engine
from autora.infra.settings import load_settings

QUERY = text(
    """
    with story_runs as (
        select w.params->>'story_id' as story_id, w.id as run_id
        from workflow_runs w
        where w.company_id = :company and w.params ? 'story_id'
    ),
    per_story as (
        select a.story_id::text as story_id,
               a.state,
               (a.created_at at time zone 'Asia/Taipei')::date as day,
               count(distinct t.id) filter (where t.name = 'draft') as drafts,
               count(distinct t.id) filter (where t.name = 'review') as reviews,
               count(distinct t.id)
                   filter (where t.name = 'review' and t.output->>'verdict' = 'revise')
                   as sent_back,
               coalesce(sum(r.cost_usd), 0) as usd
        from articles a
        join story_runs s on s.story_id = a.story_id::text
        join tasks t on t.workflow_run_id = s.run_id
        left join agent_runs r on r.task_id = t.id
        where a.company_id = :company
          and a.created_at > now() - make_interval(days => :days)
        group by a.story_id, a.state, day
    )
    select day,
           count(*) as stories,
           count(*) filter (where state = 'PUBLISHED') as published,
           count(*) filter (where state = 'REJECTED') as rejected,
           round(avg(drafts), 1) as drafts_per_story,
           sum(sent_back) as sent_back,
           sum(reviews) as reviews,
           round(sum(usd) filter (where state = 'REJECTED'), 3) as usd_rejected,
           round(sum(usd) filter (where state = 'PUBLISHED'), 3) as usd_published,
           round(sum(usd), 3) as usd_total
    from per_story
    group by day
    order by day
    """
)


async def main(days: int, company: str | None) -> None:
    engine = build_engine(load_settings().database_url)
    try:
        async with engine.connect() as conn:
            if company is None:
                company = await conn.scalar(
                    text(
                        "select company_id from articles group by company_id "
                        "order by max(created_at) desc limit 1"
                    )
                )
            rows = (await conn.execute(QUERY, {"company": company, "days": days})).all()
    finally:
        await engine.dispose()
    head = ("day", "stories", "published", "rejected", "drafts/story", "sent back", "usd rejected",
            "usd published", "usd total")  # fmt: skip
    print(f"company {company}, last {days} days")
    print(" | ".join(head))
    for r in rows:
        waste = f" ({r.usd_rejected / r.usd_total:.0%})" if r.usd_total and r.usd_rejected else ""
        print(
            f"{r.day} | {r.stories} | {r.published} | {r.rejected} | {r.drafts_per_story} | "
            f"{r.sent_back}/{r.reviews} | {r.usd_rejected or 0}{waste} | {r.usd_published or 0} | "
            f"{r.usd_total}"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--days", type=int, default=14)
    parser.add_argument("--company", default=None)
    args = parser.parse_args()
    asyncio.run(main(args.days, args.company))
