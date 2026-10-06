"""D-230: signing in with Google through the API, start to finish, against a stand-in for Google.

The browser goes to ``/start``, is sent to Google with a state, a nonce and a PKCE challenge,
and comes back to ``/callback`` with a code. These tests play the browser and Google; the API's
own code — state, PKCE, token checks, the binding rules — is the real one.
"""

import httpx
import pytest
from sqlalchemy import select

from autora.accounts import SESSION_COOKIE, Reader, ReaderIdentity
from autora_api.deps import ADMIN_COOKIE, google_dep
from tests.accounts.google_double import FakeGoogle, query_of
from tests.api.conftest import ADMIN
from tests.api.readers import PASSWORD, sign_in, token_in

SITE = "http://localhost:3000"


@pytest.fixture
def fake():
    return FakeGoogle()


@pytest.fixture
async def browser(api, fake):
    """A reader's browser (no operator token), with Google configured as the stand-in."""
    api._transport.app.dependency_overrides[google_dep] = fake.client
    async with httpx.AsyncClient(transport=api._transport, base_url="http://test") as client:
        yield client


async def _google(
    browser,
    fake,
    *,
    sub="1000",
    email="someone@gmail.com",
    verified=True,
    start="/api/auth/google/start",
    params=None,
    **claims,
):
    """Go to Google and come back, as ``sub``/``email``. Returns the callback's response."""
    leaving = await browser.get(start, params=params or {"lang": "zh-TW"})
    assert leaving.status_code == 303, leaving.text
    query = query_of(leaving.headers["location"])
    code = f"code-{sub}-{len(fake.accounts)}"
    fake.give(code, sub=sub, email=email, email_verified=verified, nonce=query["nonce"], **claims)
    return await browser.get(
        "/api/auth/google/callback", params={"state": query["state"], "code": code}
    )


def _error(response) -> str | None:
    return query_of(response.headers["location"]).get("error")


async def _google_identities(session, reader_id):
    return (
        await session.scalars(
            select(ReaderIdentity).where(
                ReaderIdentity.reader_id == reader_id, ReaderIdentity.provider == "google"
            )
        )
    ).all()


# --- first time, and after ---


async def test_a_first_google_sign_in_makes_a_reader_and_signs_them_in(browser, fake):
    back = await _google(browser, fake, email="New.Person@gmail.com")

    assert back.status_code == 303
    assert back.headers["location"] == f"{SITE}/news/zh-TW"
    assert back.cookies.get(SESSION_COOKIE)
    me = (await browser.get("/api/auth/me")).json()
    assert me["email"] == "new.person@gmail.com" and me["email_verified"] is True


async def test_the_same_google_account_is_the_same_reader(browser, fake, db_session):
    await _google(browser, fake, sub="77", email="a@gmail.com")
    first = (await browser.get("/api/auth/me")).json()["reader_id"]
    await browser.post("/api/auth/logout")

    await _google(browser, fake, sub="77", email="changed@gmail.com")
    assert (await browser.get("/api/auth/me")).json()["reader_id"] == first
    count = len((await db_session.scalars(select(Reader))).all())
    await _google(browser, fake, sub="77", email="changed@gmail.com")
    assert len((await db_session.scalars(select(Reader))).all()) == count


async def test_it_goes_back_where_it_was_asked_to(browser, fake):
    back = await _google(browser, fake, params={"lang": "en", "next": "/news/en/stocks/NVDA"})
    assert back.headers["location"] == f"{SITE}/news/en/stocks/NVDA"


async def test_a_next_that_is_not_a_path_on_the_site_is_refused(browser):
    leaving = await browser.get("/api/auth/google/start", params={"next": "https://evil.example"})
    assert leaving.status_code == 422


# --- across the two ways in ---


async def test_password_first_then_google_is_one_reader_once_the_address_is_proven(
    browser, fake, mailbox
):
    address = "both@gmail.com"
    reader_id = (await sign_in(browser, address)).json()["reader_id"]
    await browser.post("/api/auth/email/verify", json={"token": token_in(mailbox.sent[0])})
    await browser.post("/api/auth/logout")

    back = await _google(browser, fake, sub="555", email=address)
    assert _error(back) is None
    assert (await browser.get("/api/auth/me")).json()["reader_id"] == reader_id

    await browser.post("/api/auth/logout")
    again = await browser.post("/api/auth/login", json={"email": address, "password": PASSWORD})
    assert again.json()["reader_id"] == reader_id, "and the password still signs in"


async def test_google_first_then_a_password_by_reset_is_one_reader(browser, fake, mailbox):
    address = "google.first@gmail.com"
    await _google(browser, fake, sub="888", email=address)
    reader_id = (await browser.get("/api/auth/me")).json()["reader_id"]

    # registering the address changes nothing: it already has an account; its owner is emailed
    await browser.post("/api/auth/register", json={"email": address, "password": PASSWORD})
    assert "已經有帳號" in mailbox.sent[-1].text
    await browser.post("/api/auth/password/forgot", json={"email": address})
    reset = await browser.post(
        "/api/auth/password/reset",
        json={"token": token_in(mailbox.sent[-1]), "password": "my own password"},
    )
    assert reset.json()["reader_id"] == reader_id

    await browser.post("/api/auth/logout")
    signed_in = await browser.post(
        "/api/auth/login", json={"email": address, "password": "my own password"}
    )
    assert signed_in.json()["reader_id"] == reader_id
    await browser.post("/api/auth/logout")
    await _google(browser, fake, sub="888", email=address)
    assert (await browser.get("/api/auth/me")).json()["reader_id"] == reader_id


async def test_an_unproven_registration_is_not_taken_over_by_google(browser, fake, db_session):
    """Somebody registered the address first and never proved it: Google does not get that
    account, and that account keeps its password — the owner proves the address by a reset."""
    address = "victim@gmail.com"
    await browser.post("/api/auth/register", json={"email": address, "password": "squatter pw"})

    back = await _google(browser, fake, sub="999", email=address)

    assert _error(back) == "google_needs_verified_email"
    assert back.headers["location"].startswith(f"{SITE}/news/zh-TW/login?")
    assert SESSION_COOKIE not in back.cookies
    reader = await db_session.scalar(select(Reader).where(Reader.email == address))
    assert await _google_identities(db_session, reader.id) == []


async def test_an_address_google_has_not_verified_signs_nobody_in(browser, fake, db_session):
    back = await _google(browser, fake, sub="321", email="unverified@gmail.com", verified=False)
    assert _error(back) == "google_email_unverified"
    assert (
        await db_session.scalar(select(Reader).where(Reader.email == "unverified@gmail.com"))
        is None
    )


async def test_a_different_address_is_a_different_reader(browser, fake, mailbox):
    mine = (await sign_in(browser, "existing@example.com")).json()["reader_id"]
    await browser.post("/api/auth/email/verify", json={"token": token_in(mailbox.sent[0])})
    await browser.post("/api/auth/logout")

    await _google(browser, fake, sub="444", email="existing@gmail.com")
    assert (await browser.get("/api/auth/me")).json()["reader_id"] != mine


# --- the state, the code, the token ---


async def test_coming_back_without_a_state_or_with_a_made_up_one_fails(browser, fake):
    for params in ({"code": "x"}, {"state": "made-up", "code": "x"}):
        back = await browser.get("/api/auth/google/callback", params=params)
        assert back.status_code == 303 and _error(back) == "google_failed"
        assert SESSION_COOKIE not in back.cookies


async def test_a_state_is_used_once(browser, fake):
    leaving = await browser.get("/api/auth/google/start")
    query = query_of(leaving.headers["location"])
    fake.give("c1", nonce=query["nonce"])
    first = await browser.get(
        "/api/auth/google/callback", params={"state": query["state"], "code": "c1"}
    )
    assert _error(first) is None
    await browser.post("/api/auth/logout")
    again = await browser.get(
        "/api/auth/google/callback", params={"state": query["state"], "code": "c1"}
    )
    assert _error(again) == "google_failed"


async def test_a_sign_in_started_in_another_browser_cannot_be_finished_here(api, browser, fake):
    """Login CSRF: somebody starts a sign-in to their own Google account and sends the link."""
    leaving = await browser.get("/api/auth/google/start")
    query = query_of(leaving.headers["location"])
    fake.give("c2", nonce=query["nonce"])
    async with httpx.AsyncClient(transport=api._transport, base_url="http://test") as victim:
        back = await victim.get(
            "/api/auth/google/callback", params={"state": query["state"], "code": "c2"}
        )
    assert _error(back) == "google_failed" and SESSION_COOKIE not in back.cookies


async def test_a_bad_token_or_code_signs_nobody_in(browser, fake):
    impostor = FakeGoogle()
    back = await _google(browser, fake, raw_token=impostor.id_token())
    assert _error(back) == "google_failed"

    expired = await _google(browser, fake, exp=1, iat=0)
    assert _error(expired) == "google_failed"
    wrong_issuer = await _google(browser, fake, iss="https://evil.example.com")
    assert _error(wrong_issuer) == "google_failed"
    wrong_audience = await _google(browser, fake, aud="another-app")
    assert _error(wrong_audience) == "google_failed"

    fake.refuse_codes = True
    refused = await _google(browser, fake)
    assert _error(refused) == "google_failed"
    assert (await browser.get("/api/auth/me")).json() is None


async def test_saying_no_at_google_comes_back_as_cancelled(browser):
    leaving = await browser.get("/api/auth/google/start")
    query = query_of(leaving.headers["location"])
    back = await browser.get(
        "/api/auth/google/callback", params={"state": query["state"], "error": "access_denied"}
    )
    assert _error(back) == "google_cancelled"


async def test_without_a_google_client_there_is_no_google_sign_in(api):
    api._transport.app.dependency_overrides[google_dep] = lambda: None
    async with httpx.AsyncClient(transport=api._transport, base_url="http://test") as client:
        assert (await client.get("/api/auth/google/start")).status_code == 503


# --- the back office's door ---


async def test_an_admin_comes_in_with_google_to_the_back_office(browser, fake):
    back = await _google(
        browser,
        fake,
        sub="admin-sub",
        email=ADMIN,
        start="/api/admin/auth/google/start",
        params={"next": "/admin/approvals"},
    )
    assert back.headers["location"] == f"{SITE}/admin/approvals"
    assert back.cookies.get(ADMIN_COOKIE) and SESSION_COOKIE not in back.cookies
    me = await browser.get("/api/admin/auth/me")
    assert me.json() == {"via": "email", "email": ADMIN}


async def test_somebody_else_does_not_and_no_reader_is_made_for_trying(browser, fake, db_session):
    back = await _google(
        browser,
        fake,
        sub="x-sub",
        email="someone@gmail.com",
        start="/api/admin/auth/google/start",
        params={},
    )
    assert back.headers["location"] == f"{SITE}/admin/login?error=not_admin"
    assert ADMIN_COOKIE not in back.cookies
    assert (
        await db_session.scalar(select(Reader).where(Reader.email == "someone@gmail.com")) is None
    )
