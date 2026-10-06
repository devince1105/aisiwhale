"""D-230: the reader's side of the API — an address and a password, the emails about them, and
the cookie that proves who somebody is.

These are the site's own endpoints: no operator token, and nothing about a reader is returned to
anybody who does not hold their cookie. Registering and asking for a reset answer the same for
any address; a failed sign-in says only that the address or password is wrong.
"""

import httpx
import pytest
from sqlalchemy import select

from autora.accounts import SESSION_COOKIE, ReaderIdentity
from tests.api.readers import PASSWORD, sign_in, token_in

ADDRESS = "reader@example.com"


@pytest.fixture
async def site(api):
    """The same app without the operator's token: what a reader's browser has."""
    async with httpx.AsyncClient(transport=api._transport, base_url="http://test") as client:
        yield client


async def _register(site, address=ADDRESS, password=PASSWORD):
    return await site.post("/api/auth/register", json={"email": address, "password": password})


async def _login(site, address=ADDRESS, password=PASSWORD):
    return await site.post("/api/auth/login", json={"email": address, "password": password})


# --- registering ---


async def test_registering_emails_a_link_and_the_password_then_signs_in(site, mailbox):
    assert (await _register(site)).status_code == 202
    (message,) = mailbox.sent
    assert message.to == ADDRESS and "確認" in message.subject
    assert "/news/zh-TW/verify-email?token=" in message.text

    signed_in = await _login(site)
    assert signed_in.status_code == 200
    body = signed_in.json()
    assert body["email"] == ADDRESS and body["email_verified"] is False
    assert signed_in.cookies.get(SESSION_COOKIE), "the browser leaves with a session"
    assert (await site.get("/api/auth/me")).json()["email"] == ADDRESS


async def test_registering_says_the_same_thing_for_an_address_that_has_an_account(site, mailbox):
    """The form must not answer "is this person a reader here?"."""
    new = await _register(site)
    taken = await _register(site, "Reader@Example.com", "a different password")

    assert (new.status_code, new.text) == (taken.status_code, taken.text)
    first, second = mailbox.sent
    assert first.to == second.to == ADDRESS
    assert "verify-email?token=" in first.text
    assert "已經有帳號" in second.text and "token=" not in second.text
    assert (await _login(site, password="a different password")).status_code == 401, (
        "and the account keeps its own password"
    )


async def test_one_address_is_one_account_however_it_is_typed(site, db_session):
    await _register(site, " Reader@EXAMPLE.com ")
    await _register(site, "reader@example.com")
    rows = (
        await db_session.scalars(select(ReaderIdentity).where(ReaderIdentity.subject == ADDRESS))
    ).all()
    assert len(rows) == 1
    assert (await _login(site, "READER@example.com")).status_code == 200


async def test_what_cannot_be_registered(site, mailbox):
    assert (await _register(site, "not-an-address")).status_code == 422
    assert (await _register(site, password="short")).status_code == 422
    assert mailbox.sent == []


async def test_the_password_is_never_stored_or_returned(site, db_session):
    answer = await _register(site)
    signed_in = await _login(site)
    row = await db_session.scalar(select(ReaderIdentity).where(ReaderIdentity.subject == ADDRESS))
    assert row.password_hash.startswith("$argon2id$") and PASSWORD not in row.password_hash
    assert PASSWORD not in answer.text and PASSWORD not in signed_in.text


# --- signing in and out ---


async def test_a_wrong_password_and_an_unknown_address_get_the_same_answer(site):
    await _register(site)
    wrong = await _login(site, password="not the password")
    unknown = await _login(site, "nobody@example.com")
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["detail"] == unknown.json()["detail"]
    assert SESSION_COOKIE not in wrong.cookies


async def test_nobody_is_nobody(site):
    assert (await site.get("/api/auth/me")).json() is None


async def test_signing_out_ends_the_session(site):
    signed_in = await sign_in(site, ADDRESS)
    cookie = signed_in.cookies[SESSION_COOKIE]
    assert (await site.post("/api/auth/logout")).status_code == 204
    assert (await site.get("/api/auth/me")).json() is None
    site.cookies.set(SESSION_COOKIE, cookie)  # even kept, it no longer works
    assert (await site.get("/api/auth/me")).json() is None


async def test_a_made_up_cookie_proves_nothing(site):
    site.cookies.set(SESSION_COOKIE, "not-a-real-session")
    assert (await site.get("/api/auth/me")).json() is None


async def test_the_retired_sign_in_link_is_gone(site):
    assert (await site.post("/api/auth/link", json={"email": ADDRESS})).status_code in (404, 405)
    assert (await site.post("/api/auth/verify", json={"token": "x" * 20})).status_code in (404, 405)


# --- proving the address ---


async def test_the_link_proves_the_address_once_and_signs_nobody_in(site, mailbox):
    await _register(site)
    token = token_in(mailbox.sent[0])

    verified = await site.post("/api/auth/email/verify", json={"token": token})
    assert verified.status_code == 204 and SESSION_COOKIE not in verified.cookies
    assert (await _login(site)).json()["email_verified"] is True

    again = await site.post("/api/auth/email/verify", json={"token": token})
    assert again.status_code == 400 and "no longer works" in again.text


async def test_a_new_link_is_for_the_signed_in_and_only_while_unproven(site, mailbox):
    assert (await site.post("/api/auth/email/resend", json={})).status_code == 401
    await sign_in(site, ADDRESS)
    mailbox.sent.clear()

    assert (await site.post("/api/auth/email/resend", json={})).status_code == 202
    (message,) = mailbox.sent
    await site.post("/api/auth/email/verify", json={"token": token_in(message)})
    assert (await site.post("/api/auth/email/resend", json={})).status_code == 202
    assert len(mailbox.sent) == 1, "nothing left to prove, nothing sent"


# --- forgetting ---


async def test_asking_for_a_reset_says_the_same_thing_for_any_address(site, mailbox):
    await _register(site)
    mailbox.sent.clear()
    known = await site.post("/api/auth/password/forgot", json={"email": ADDRESS})
    stranger = await site.post("/api/auth/password/forgot", json={"email": "nobody@example.com"})
    rubbish = await site.post("/api/auth/password/forgot", json={"email": "not-an-address"})

    assert (known.status_code, known.text) == (stranger.status_code, stranger.text)
    assert (rubbish.status_code, rubbish.text) == (known.status_code, known.text)
    (message,) = mailbox.sent
    assert message.to == ADDRESS and "/news/zh-TW/reset-password?token=" in message.text


async def test_a_reset_sets_the_password_signs_out_elsewhere_and_signs_in_here(api, site, mailbox):
    first = await sign_in(site, ADDRESS)
    elsewhere = first.cookies[SESSION_COOKIE]
    await site.post("/api/auth/password/forgot", json={"email": ADDRESS})
    token = token_in(mailbox.sent[-1])

    async with httpx.AsyncClient(transport=api._transport, base_url="http://test") as other:
        reset = await other.post(
            "/api/auth/password/reset", json={"token": token, "password": "a brand new one"}
        )
        assert reset.status_code == 200, reset.text
        assert reset.json()["email_verified"] is True, "the reset link proved the address"
        assert (await other.get("/api/auth/me")).json()["email"] == ADDRESS

    site.cookies.set(SESSION_COOKIE, elsewhere)
    assert (await site.get("/api/auth/me")).json() is None, "the old session ended"
    assert (await _login(site)).status_code == 401
    assert (await _login(site, password="a brand new one")).status_code == 200


async def test_a_reset_link_works_once(site, mailbox):
    await _register(site)
    await site.post("/api/auth/password/forgot", json={"email": ADDRESS})
    token = token_in(mailbox.sent[-1])
    body = {"token": token, "password": "a brand new one"}
    assert (await site.post("/api/auth/password/reset", json=body)).status_code == 200
    again = await site.post("/api/auth/password/reset", json=body)
    assert again.status_code == 400 and "no longer works" in again.text


async def test_a_short_new_password_is_refused_and_keeps_the_link(site, mailbox):
    await _register(site)
    await site.post("/api/auth/password/forgot", json={"email": ADDRESS})
    token = token_in(mailbox.sent[-1])
    short = await site.post("/api/auth/password/reset", json={"token": token, "password": "short"})
    assert short.status_code == 422
    good = await site.post(
        "/api/auth/password/reset", json={"token": token, "password": "long enough"}
    )
    assert good.status_code == 200


# --- rate limits ---


async def test_signing_in_too_often_is_refused_for_a_while(site):
    await _register(site)
    for _ in range(10):
        assert (await _login(site, password="guess")).status_code == 401
    blocked = await _login(site)
    assert blocked.status_code == 429, "even the right password waits once the address is limited"


async def test_one_network_cannot_try_endless_addresses(site, db_session):
    """The network is counted first: an address is only counted while its network may still try,
    so a flood of made-up addresses stops at the network's limit and adds no more keys."""
    from autora.accounts import AuthRateLimit

    for n in range(30):
        await _login(site, f"made-up-{n}@example.com", "guess")
    keys_before = len((await db_session.scalars(select(AuthRateLimit))).all())
    for n in range(30, 40):
        assert (await _login(site, f"made-up-{n}@example.com", "guess")).status_code == 429
    assert len((await db_session.scalars(select(AuthRateLimit))).all()) == keys_before


async def test_asking_for_resets_too_often_is_refused(site):
    for _ in range(3):
        await site.post("/api/auth/password/forgot", json={"email": ADDRESS})
    assert (
        await site.post("/api/auth/password/forgot", json={"email": ADDRESS})
    ).status_code == 429


# --- the cookie ---


async def test_the_cookie_counts_on_the_site_s_domain_when_one_is_set(api, site):
    """D-153: api.aisiwhale.com sets it for aisiwhale.com, whose server must read it too."""
    from autora.infra.settings import load_settings
    from autora_api.deps import settings_dep

    app = api._transport.app
    base = app.dependency_overrides[settings_dep]()
    app.dependency_overrides[settings_dep] = lambda: load_settings(
        database_url=base.database_url,
        api_bearer_token=base.api_bearer_token.get_secret_value(),
        cookie_domain=".aisiwhale.com",
        site_base_url="https://aisiwhale.com",
    )
    signed_in = await sign_in(site, ADDRESS)
    header = signed_in.headers["set-cookie"].lower()
    assert "domain=.aisiwhale.com" in header and "secure" in header and "httponly" in header
    assert "samesite=lax" in header
    out = await site.post("/api/auth/logout")
    assert "domain=.aisiwhale.com" in out.headers["set-cookie"].lower()


async def test_a_forwarded_for_header_does_not_buy_a_fresh_limit(site):
    """X-Forwarded-For's first entry is the client's to write: changing it is not a new network.
    (Behind Cloudflare the network is CF-Connecting-IP, which Cloudflare sets itself.)"""
    for n in range(30):
        await site.post(
            "/api/auth/login",
            json={"email": f"spoof-{n}@example.com", "password": "guess"},
            headers={"X-Forwarded-For": f"10.0.{n}.1"},
        )
    blocked = await site.post(
        "/api/auth/login",
        json={"email": "spoof-new@example.com", "password": "guess"},
        headers={"X-Forwarded-For": "10.9.9.9"},
    )
    assert blocked.status_code == 429


async def test_cloudflare_s_connecting_address_is_the_network(site):
    for n in range(30):
        await site.post(
            "/api/auth/login",
            json={"email": f"cf-{n}@example.com", "password": "guess"},
            headers={"CF-Connecting-IP": "203.0.113.7"},
        )
    other = await site.post(
        "/api/auth/login",
        json={"email": "cf-other@example.com", "password": "guess"},
        headers={"CF-Connecting-IP": "203.0.113.8"},
    )
    assert other.status_code == 401, "another network has its own limit"
