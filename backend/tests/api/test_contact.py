"""聯絡我們: a reader's message reaches the operator's inbox, answerable to the reader (D-165);
and floods and bots do not get through, nor use up the sign-in links' email quota (D-166)."""

import httpx
import pytest

from autora.infra.settings import load_settings
from autora_api.deps import settings_dep
from autora_api.routers import contact

MESSAGE = {
    "name": "王小明",
    "email": "Reader@Example.com",
    "topic": "membership",
    "message": "請問月繳會員可以開發票嗎？謝謝。",
    "elapsed_ms": 8000,
}


@pytest.fixture
async def site(api):
    contact.recent._seen.clear()
    contact.daily.day, contact.daily.sent = None, 0
    async with httpx.AsyncClient(transport=api._transport, base_url="http://test") as client:
        client.app = api._transport.app  # type: ignore[attr-defined]
        yield client


def _configure(site, db_settings, **settings):
    site.app.dependency_overrides[settings_dep] = lambda: load_settings(
        database_url=db_settings.database_url, **settings
    )


async def test_a_message_reaches_the_inbox_and_a_reply_goes_to_the_reader(site, mailbox):
    response = await site.post("/api/public/contact", json=MESSAGE)
    assert response.status_code == 202
    [sent] = mailbox.sent
    assert sent.to == "service@aisiwhale.com"
    assert sent.reply_to == "reader@example.com"
    assert sent.subject == "【聯絡我們】會員與付款：王小明"
    assert "請問月繳會員可以開發票嗎" in sent.text and "王小明" in sent.text
    assert "電話" not in sent.text  # left empty, left out


async def test_a_phone_and_a_company_come_along_when_given(site, mailbox):
    body = MESSAGE | {"topic": "partnership", "phone": "0912-345-678", "company": "某某投顧"}
    assert (await site.post("/api/public/contact", json=body)).status_code == 202
    [sent] = mailbox.sent
    assert "電話：0912-345-678" in sent.text and "公司：某某投顧" in sent.text


async def test_a_bot_is_told_sent_and_nothing_is_sent(site, mailbox):
    filled = await site.post("/api/public/contact", json=MESSAGE | {"website": "http://x"})
    hurried = await site.post("/api/public/contact", json=MESSAGE | {"elapsed_ms": 400})
    assert filled.status_code == hurried.status_code == 202
    assert mailbox.sent == []


async def test_what_is_not_a_message_is_refused(site, mailbox):
    for wrong in ({"email": "nope"}, {"message": "hi"}, {"topic": "x"}):
        assert (await site.post("/api/public/contact", json=MESSAGE | wrong)).status_code == 422
    assert mailbox.sent == []


async def test_a_few_an_hour_from_one_address(site, mailbox):
    for _ in range(contact.PER_HOUR):
        assert (await site.post("/api/public/contact", json=MESSAGE)).status_code == 202
    assert (await site.post("/api/public/contact", json=MESSAGE)).status_code == 429
    assert len(mailbox.sent) == contact.PER_HOUR
    # another reader is not held back by this one
    other = await site.post(
        "/api/public/contact", json=MESSAGE, headers={"cf-connecting-ip": "203.0.113.9"}
    )
    assert other.status_code == 202


async def test_from_everyone_together_a_day_has_a_ceiling(site, mailbox, db_settings):
    # D-166: many addresses at once (a botnet) still cannot use up the sign-in links' quota
    _configure(site, db_settings, contact_daily_cap=3)
    answers = []
    for n in range(5):
        response = await site.post(
            "/api/public/contact", json=MESSAGE, headers={"cf-connecting-ip": f"198.51.100.{n}"}
        )
        answers.append(response.status_code)
    assert answers == [202, 202, 202, 429, 429]
    assert len(mailbox.sent) == 3


async def test_with_turnstile_each_message_needs_its_own_token(site, mailbox, db_settings):
    # D-166: changing address does not help — every message carries a token Cloudflare checks
    _configure(site, db_settings, turnstile_secret_key="secret")
    asked = []

    async def verifier(secret, token, address):
        asked.append((secret, token, address))
        return token == "good"

    site.app.dependency_overrides[contact.turnstile_dep] = lambda: verifier

    missing = await site.post("/api/public/contact", json=MESSAGE)
    forged = await site.post("/api/public/contact", json=MESSAGE | {"turnstile_token": "bad"})
    earned = await site.post(
        "/api/public/contact",
        json=MESSAGE | {"turnstile_token": "good"},
        headers={"cf-connecting-ip": "192.0.2.7"},
    )
    assert (missing.status_code, forged.status_code, earned.status_code) == (403, 403, 202)
    assert len(mailbox.sent) == 1
    assert asked[-1] == ("secret", "good", "192.0.2.7")  # asked with the reader's address
