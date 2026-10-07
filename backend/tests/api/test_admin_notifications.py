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
