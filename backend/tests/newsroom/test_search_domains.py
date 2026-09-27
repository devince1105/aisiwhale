"""D-057: a search can be kept to named sites — Tavily's include_domains, and the fixture alike."""

from datetime import UTC, datetime

from autora.infra.search.fixture import FixtureDocument, FixtureSearchProvider


async def test_the_fixture_keeps_to_the_sites_named():
    docs = [
        FixtureDocument(url="https://www.blackrock.com/weekly", title="Outlook", snippet="outlook"),
        FixtureDocument(url="https://www.quora.com/q", title="Outlook?", snippet="outlook"),
    ]
    provider = FixtureSearchProvider(docs, now=datetime(2026, 9, 27, tzinfo=UTC))
    everywhere = await provider.search("outlook", k=5)
    assert len(everywhere.results) == 2
    kept = await provider.search("outlook", k=5, domains=["blackrock.com"])
    assert [r.url for r in kept.results] == ["https://www.blackrock.com/weekly"]
