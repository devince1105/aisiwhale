"""AD-10: what waits for a person to decide reaches them — the daily email to the admins who
decide (owners and editors, proven, not turned off), with each company's oldest first and what
runs out soon; nothing waiting, no email; and each admin's own switch for it."""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from autora.accounts import credentials
from autora.accounts.admin_digest import compose, recipients, send_digest, waiting
from autora.accounts.models import Reader
from autora.db.models import DIGEST_ROLES, AdminPref, AdminRole, Approval
from autora.infra.email import ConsoleSender
from autora_api import permissions
from autora_api.deps import ADMIN_COOKIE
from tests.api.conftest import ADMIN
from tests.conftest import unique_company

PASSWORD = "correct horse battery"
NOW = datetime(2026, 10, 8, 7, 5, tzinfo=UTC)


def test_the_digest_goes_to_the_roles_that_decide():
    assert DIGEST_ROLES == {
        role
        for role in ("owner", "editor", "finance", "viewer")
        if "approvals:decide" in permissions.permissions_of(role)
    }


async def _reader(session, address, *, role=None, prove=True, digest=None):
    outcome = await credentials.register(session, address, PASSWORD)
    if prove:
        await credentials.verify_email(session, outcome.verify_token)
    reader = await session.scalar(select(Reader).where(Reader.email == address))
    if role:
        session.add(
            AdminRole(reader_id=reader.id, role=role, granted_by={"kind": "human", "id": "t"})
        )
    if digest is not None:
        session.add(AdminPref(reader_id=reader.id, approvals_digest=digest))
    await session.flush()
    return reader


async def _approval(session, company, summary, *, ago, expires_in=None):
    approval = Approval(
        company_id=company.id,
        kind="article",
        ref_type="test",
        ref_id=uuid.uuid4(),
        summary=summary,
        requested_by={"kind": "system", "id": "test"},
        created_at=NOW - ago,
        expires_at=NOW + expires_in if expires_in is not None else None,
    )
    session.add(approval)
    await session.flush()
    return approval


async def test_who_gets_it(db_session):
    owner = await _reader(db_session, "owner@digest.test")
    await _reader(db_session, "ed@digest.test", role="editor")
    await _reader(db_session, "fin@digest.test", role="finance")
    await _reader(db_session, "look@digest.test", role="viewer")
    await _reader(db_session, "quiet@digest.test", role="owner", digest=False)
    await _reader(db_session, "unproven@digest.test", role="editor", prove=False)
    got = await recipients(db_session, [owner.email, "nobody-signed-up@digest.test"])
    assert got == ["ed@digest.test", "owner@digest.test"]


async def test_what_it_says(db_session):
    company = await unique_company(db_session, "digest")
    await _approval(
        db_session,
        company,
        "核准發布：台股創新高",
        ago=timedelta(hours=5),
        expires_in=timedelta(minutes=50),
    )
    await _approval(
        db_session,
        company,
        "核准發布：美股收黑",
        ago=timedelta(minutes=20),
        expires_in=timedelta(hours=20),
    )
    groups = [g for g in await waiting(db_session) if g.company.id == company.id]
    message = compose("ed@digest.test", groups, "https://aisiwhale.com/", NOW)
    assert message.to == "ed@digest.test"
    assert message.subject == "【艾矽鯨後台】2 件等待審批（1 件 2 小時內到期）"
    first, second = message.text.index("台股創新高"), message.text.index("美股收黑")
    assert first < second, "the oldest first"
    assert "・核准發布：台股創新高（已等 5 小時，50 分鐘後到期（快到了））" in message.text
    assert "・核准發布：美股收黑（已等 20 分鐘，20 小時後到期）" in message.text
    assert f"https://aisiwhale.com/admin/approvals?company={company.id}" in message.text
    assert "關掉「每日 email 摘要」" in message.text


async def _published(session, company) -> datetime:
    """An article published in ``company`` now; when, as the event says."""
    from autora.domains.newsroom.events import ArticlePublished
    from autora.runtime.actor import Actor
    from autora.runtime.events.outbox import emit
    from autora.runtime.events.schema import new_event

    article_id = uuid.uuid4()
    envelope = new_event(
        ArticlePublished(article_id=article_id, slug="s", langs=["zh-TW"], url="/news/zh-TW/a"),
        company_id=company.id,
        actor=Actor.system("publisher"),
        aggregate_type="article",
        aggregate_id=article_id,
    )
    await emit(session, envelope)
    await session.flush()
    return envelope.occurred_at


async def test_a_stalled_newsroom_is_told_with_who_is_paused(db_session):
    """D-258: from 2026-10-18 the writer was paused for four days, said only in the office's
    team chat. A day without an article is in the email, with whoever is paused."""
    from autora.accounts.admin_digest import quiet
    from autora.company.agents.roster import hire_agent
    from autora.company.organization import bootstrap_executive, role_by_key
    from autora.runtime.actor import Actor

    company = await unique_company(db_session, "stalled")
    published = await _published(db_session, company)
    await bootstrap_executive(db_session, company.id, actor=Actor.human("t"))
    writer = await hire_agent(
        db_session, company_id=company.id, role="ceo", display_name="胡蝶忍",
        actor=Actor.human("t"), position=await role_by_key(db_session, company.id, "ceo"),
    )  # fmt: skip
    writer.status = "paused"
    await db_session.flush()
    later = published + timedelta(hours=40)

    (stalled,) = [q for q in await quiet(db_session, later) if q.company.id == company.id]
    assert stalled.hours == 40 and stalled.paused == ["胡蝶忍"]
    message = compose("owner@digest.test", [], "https://aisiwhale.com", later, [stalled])
    assert message.subject == "【艾矽鯨後台】編輯部已 40 小時沒有發文"
    assert "暫停中的員工：胡蝶忍" in message.text
    assert f"https://aisiwhale.com/admin/agents?company={company.id}" in message.text


async def test_a_desk_publishing_today_or_gone_for_a_month_is_not_told(db_session):
    from autora.accounts.admin_digest import quiet

    company = await unique_company(db_session, "busy")
    published = await _published(db_session, company)

    def told(at):
        return any(q.company.id == company.id for q in at)

    assert not told(await quiet(db_session, published + timedelta(hours=3)))
    assert told(await quiet(db_session, published + timedelta(days=2)))
    assert not told(await quiet(db_session, published + timedelta(days=31))), (
        "a demo, a closed desk"
    )


async def test_nothing_waiting_sends_nothing_and_a_bounce_stops_no_one(db_session):
    sender = ConsoleSender(echo=False)
    await _reader(db_session, "ed2@digest.test", role="editor")
    # whatever else the test database holds, a company with nothing pending adds no email
    before = await send_digest(db_session, sender, admin_emails=[], site_base_url="x", now=NOW)
    company = await unique_company(db_session, "digest2")
    await _approval(db_session, company, "核准：x", ago=timedelta(hours=1))
    await _reader(db_session, "ed3@digest.test", role="editor")

    class Flaky(ConsoleSender):
        async def send(self, message):
            if message.to == "ed2@digest.test":
                raise RuntimeError("bounced")
            await super().send(message)

    flaky = Flaky(echo=False)
    sent = await send_digest(db_session, flaky, admin_emails=[], site_base_url="x", now=NOW)
    assert [m.to for m in flaky.sent] == ["ed3@digest.test"] and sent == 1
    assert before in (0, 1)


async def test_each_admin_turns_it_off_for_themselves(api, db_session):
    await _reader(db_session, "self@digest.test", role="viewer")
    api.cookies.clear()
    login = await api.post(
        "/api/admin/auth/login",
        json={"email": "self@digest.test", "password": PASSWORD},
        headers={"Authorization": ""},
    )
    api.cookies.set(ADMIN_COOKIE, login.cookies[ADMIN_COOKIE])
    anon = {"Authorization": ""}
    assert (await api.get("/api/admin/me/prefs", headers=anon)).json() == {"approvals_digest": True}
    changed = await api.put("/api/admin/me/prefs", json={"approvals_digest": False}, headers=anon)
    assert changed.status_code == 200, changed.text
    assert (await api.get("/api/admin/me/prefs", headers=anon)).json() == {
        "approvals_digest": False
    }
    api.cookies.clear()
    # the token is nobody's
    assert (await api.get("/api/admin/me/prefs")).status_code == 409
    assert ADMIN  # the owner from ADMIN_EMAILS has prefs like anybody signed in


def test_the_worker_runs_the_digest(committed):
    """The schedule migration 0080 writes has a handler in the worker."""
    from autora.accounts.admin_digest import DIGEST_SCHEDULE
    from autora.app import build_scheduler

    scheduler = build_scheduler(None, committed, f"test-{uuid.uuid4().hex[:6]}")
    assert DIGEST_SCHEDULE in scheduler._handlers
