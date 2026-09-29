"""D-117: AI Media's kill criterion in the base currency (NT$), and a mission that says the site
earns nothing yet on purpose — the two things the CEO misread when it paused the newsroom."""

from autora.company.organization import business_unit_by_key
from autora.domains.newsroom import organization
from autora.domains.newsroom.organization import BUSINESS_UNIT, KILL_CRITERIA
from autora.runtime.actor import Actor
from tests.conftest import unique_company


def test_the_cap_is_nt_dollars_not_the_us_dollars_it_was_written_in():
    rule = KILL_CRITERIA["auto_pause_if"]
    assert rule["metric"] == "cost_per_published_article"
    # an article costs about NT$4 to make; the cap is about the US$3 it was meant to be
    assert rule["value"] == 100.0 and rule["unit"] == "TWD per published article"


async def test_a_new_newsroom_is_built_with_them(db_session):
    company = await unique_company(db_session, "media")
    await organization.build(db_session, company.id, actor=Actor.human("operator"))
    unit = await business_unit_by_key(db_session, company.id, BUSINESS_UNIT)
    assert unit.kill_criteria == KILL_CRITERIA
    assert "no revenue is expected yet" in unit.mission
