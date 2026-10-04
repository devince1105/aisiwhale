"""D-193: the admin can see when the AI staff work."""

from autora.infra.settings import load_settings
from autora_api.deps import settings_dep
from tests.api.conftest import TOKEN


async def test_always_at_work_without_shifts(api):
    got = (await api.get("/api/office-hours")).json()
    assert got["shifts"] == [] and got["on_duty"] is True and got["next_start"] is None


async def test_shifts_and_the_next_clock_in(api, db_settings):
    api._transport.app.dependency_overrides[settings_dep] = lambda: load_settings(
        database_url=db_settings.database_url,
        api_bearer_token=TOKEN,
        worker_shifts="00:00-00:01",
        worker_days="mon-sun",
        worker_timezone="UTC",
    )
    got = (await api.get("/api/office-hours", headers={"Authorization": f"Bearer {TOKEN}"})).json()
    assert got["shifts"] == ["00:00-00:01"] and got["timezone"] == "UTC"
    if not got["on_duty"]:
        assert got["next_start"].endswith(("T00:00:00Z", "T00:00:00+00:00"))
