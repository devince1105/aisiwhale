"""D-178: the office's style is the company's, set in the back office; the public site's
AI 編輯部 is shown in its company's style, and a reader cannot change it."""

import uuid

import httpx

from tests.conftest import unique_company


async def test_the_back_office_sets_the_style_and_the_site_shows_it(api, db_session):
    company = await unique_company(db_session, "office-theme")
    path = f"/api/companies/{company.id}/office-theme"

    assert (await api.get(path)).json() == {"theme": "muji"}  # until one is chosen
    assert (await api.put(path, json={"theme": "cyber"})).json() == {"theme": "cyber"}
    assert (await api.get(path)).json() == {"theme": "cyber"}

    async with httpx.AsyncClient(transport=api._transport, base_url="http://test") as public:
        got = await public.get("/api/public/office-theme", params={"company": company.slug})
        assert got.json() == {"theme": "cyber"}
        unknown = await public.get("/api/public/office-theme", params={"company": "nobody"})
        assert unknown.json() == {"theme": "muji"}
        assert (await public.get("/api/public/office-theme")).json() == {"theme": "muji"}
        # a reader cannot set it
        refused = await public.put(path, json={"theme": "muji"})
        assert refused.status_code == 401


async def test_only_a_style_the_office_has(api, db_session):
    company = await unique_company(db_session, "office-theme-bad")
    path = f"/api/companies/{company.id}/office-theme"
    assert (await api.put(path, json={"theme": "neon"})).status_code == 422
    missing = await api.put(f"/api/companies/{uuid.uuid4()}/office-theme", json={"theme": "muji"})
    assert missing.status_code == 404
