"""D-055, D-230: the back office lets in a reader who signed in — with their password or with
Google — whose address is on ADMIN_EMAILS and proven to be theirs.

Authentication is the readers' own; authorization is apart from it. Knowing an admin's address,
even registering it, opens nothing; a reader's cookie never opens the back office. An address on
ADMIN_EMAILS with no account cannot be registered through the site at all: its owner comes in by
Google or a password reset, which prove the address themselves.
"""

from sqlalchemy import select

from autora.accounts import Reader, credentials
from autora.db.models import CommandRecord
from autora.infra.settings import load_settings
from autora_api.deps import ADMIN_COOKIE, settings_dep
from tests.api.conftest import ADMIN
from tests.api.readers import PASSWORD
from tests.conftest import unique_company

ANON = {"Authorization": ""}
LOGIN, ME = "/api/admin/auth/login", "/api/admin/auth/me"


def _post(api, path, body=None):
    """As a browser would: no operator token, only whatever cookie it holds."""
    return api.post(path, json=body, headers=ANON)


def _get(api, path):
    return api.get(path, headers=ANON)


async def _admin_account(db_session, address=ADMIN, *, prove=True) -> None:
    """An account for the address, made by the accounts layer itself and (unless told not to)
    proven — as an existing admin's is. The site's own registration will not make one for an
    address on ADMIN_EMAILS (see the tests at the end)."""
    outcome = await credentials.register(db_session, address, PASSWORD)
    if prove:
        await credentials.verify_email(db_session, outcome.verify_token)
    await db_session.flush()


async def _sign_in(api, db_session) -> str:
    await _admin_account(db_session)
    response = await _post(api, LOGIN, {"email": ADMIN, "password": PASSWORD})
    assert response.status_code == 200, response.text
    assert response.json() == {"via": "email", "email": ADMIN}
    cookie = response.cookies[ADMIN_COOKIE]
    api.cookies.set(ADMIN_COOKIE, cookie)
    return cookie


async def test_an_admin_signed_in_uses_the_back_office_without_the_token(api, db_session, mailbox):
    company = await unique_company(db_session, "adm")
    assert (await _get(api, f"/api/companies/{company.id}/finance")).status_code == 401
    await _sign_in(api, db_session)
    assert (await _get(api, f"/api/companies/{company.id}/finance")).status_code == 200
    assert (await _get(api, ME)).json() == {"via": "email", "email": ADMIN}

    # what an admin does is recorded as theirs, by id — never by address (D-024)
    await api.post(
        f"/api/companies/{company.id}/finance/budgets", json={"amount": "10"}, headers=ANON
    )
    reader = await db_session.scalar(select(Reader).where(Reader.email == ADMIN))
    log = await db_session.scalar(
        select(CommandRecord).where(CommandRecord.company_id == company.id)
    )
    assert log.actor == {"kind": "human", "id": f"admin:{reader.id}"}


async def test_an_unproven_admin_address_opens_nothing(api, db_session, mailbox):
    """Somebody registers the admin's address (a list, not a secret): unproven, not let in."""
    await _admin_account(db_session, prove=False)
    response = await _post(api, LOGIN, {"email": ADMIN, "password": PASSWORD})
    assert response.status_code == 403 and ADMIN_COOKIE not in response.cookies
    assert (await _get(api, ME)).status_code == 401


async def test_a_reader_off_the_list_is_not_let_in(api, db_session, mailbox):
    await _admin_account(db_session, "reader@example.com")
    response = await _post(api, LOGIN, {"email": "reader@example.com", "password": PASSWORD})
    assert response.status_code == 403 and ADMIN_COOKIE not in response.cookies


async def test_a_wrong_password_says_only_that(api, db_session, mailbox):
    await _admin_account(db_session)
    wrong = await _post(api, LOGIN, {"email": ADMIN, "password": "not it"})
    unknown = await _post(api, LOGIN, {"email": "nobody@example.com", "password": "not it"})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["detail"] == unknown.json()["detail"]


async def test_the_token_still_opens_the_back_office(api, db_session):
    assert (await api.get(ME)).json() == {"via": "token", "email": None}
    assert (await _get(api, ME)).status_code == 401


async def test_off_the_list_means_out_at_once(api, db_session, db_settings, mailbox):
    await _sign_in(api, db_session)
    app = api._transport.app
    app.dependency_overrides[settings_dep] = lambda: load_settings(
        database_url=db_settings.database_url, api_bearer_token="x", admin_emails=[]
    )
    assert (await _get(api, ME)).status_code == 401


async def test_a_reader_s_cookie_does_not_open_it(api, db_session, mailbox):
    """The same person signed in to the site is not thereby in the back office."""
    await _admin_account(db_session)
    site = await _post(api, "/api/auth/login", {"email": ADMIN, "password": PASSWORD})
    assert site.status_code == 200
    assert (await _get(api, ME)).status_code == 401


async def test_signing_out_ends_the_session(api, db_session, mailbox):
    cookie = await _sign_in(api, db_session)
    assert (await _post(api, "/api/admin/auth/logout")).status_code == 204
    api.cookies.set(ADMIN_COOKIE, cookie)  # even kept, it no longer works
    assert (await _get(api, ME)).status_code == 401


async def test_there_is_no_emailed_link_into_the_back_office_any_more(api, db_session):
    for path in ("/api/admin/auth/link", "/api/admin/auth/verify"):
        assert (await _post(api, path, {"email": ADMIN})).status_code in (404, 405)


# --- registering an address on ADMIN_EMAILS (D-230) ---


async def _register(api, address, password=PASSWORD):
    return await _post(api, "/api/auth/register", {"email": address, "password": password})


async def test_a_new_admin_address_cannot_be_registered_through_the_site(api, db_session, mailbox):
    """Somebody registers the admin's address before the admin has an account: nothing is made,
    their password opens nothing, and the mailbox's owner is told the ways in."""
    answer = await _register(api, ADMIN, "the squatter's password")

    assert answer.status_code == 202
    assert await db_session.scalar(select(Reader).where(Reader.email == ADMIN)) is None
    assert (
        await _post(api, "/api/auth/login", {"email": ADMIN, "password": "the squatter's password"})
    ).status_code == 401
    assert (
        await _post(api, LOGIN, {"email": ADMIN, "password": "the squatter's password"})
    ).status_code == 401
    (message,) = mailbox.sent
    assert message.to == ADMIN and "token=" not in message.text
    assert "Google" in message.text and "forgot-password" in message.text


async def test_the_answer_says_nothing_about_why(api, db_session, mailbox):
    """A new admin address, a new ordinary address and a taken one all get the same answer."""
    await _admin_account(db_session, "taken@example.com")
    blocked = await _register(api, ADMIN)
    new = await _register(api, "newcomer@example.com")
    taken = await _register(api, "taken@example.com")

    assert blocked.status_code == new.status_code == taken.status_code == 202
    assert blocked.text == new.text == taken.text
    assert {k.lower() for k in blocked.headers} == {k.lower() for k in new.headers}
    assert len(mailbox.sent) == 3, "each address's owner hears about it, in their own mailbox"


async def test_an_existing_admin_account_is_left_as_it_was(api, db_session, mailbox):
    """The admin already has an account (as every admin in production does): registering the
    address again changes nothing, and the admin still signs in with their own password."""
    await _admin_account(db_session)
    answer = await _register(api, ADMIN, "somebody else's password")

    assert answer.status_code == 202
    (message,) = mailbox.sent
    assert "已經有帳號" in message.text
    assert (
        await _post(api, LOGIN, {"email": ADMIN, "password": "somebody else's password"})
    ).status_code == 401
    signed_in = await _post(api, LOGIN, {"email": ADMIN, "password": PASSWORD})
    assert signed_in.status_code == 200 and signed_in.json()["email"] == ADMIN


async def test_ordinary_addresses_still_register(api, db_session, mailbox):
    assert (await _register(api, "reader@example.com")).status_code == 202
    assert "verify-email?token=" in mailbox.sent[-1].text
    signed_in = await _post(
        api, "/api/auth/login", {"email": "reader@example.com", "password": PASSWORD}
    )
    assert signed_in.status_code == 200


async def test_a_new_admin_comes_in_by_google_instead(api, db_session):
    """Google proves the address itself, so it can make the admin's account (D-230)."""
    from autora.accounts import google
    from autora.accounts.google import GoogleAccount

    reader = await google.sign_in(
        db_session, GoogleAccount(sub="admin-google-sub", email=ADMIN, email_verified=True)
    )
    assert reader.email == ADMIN and await credentials.email_verified(db_session, reader)
