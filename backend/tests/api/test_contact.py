"""D-165: 聯絡我們 — a reader's message reaches the operator's inbox, answerable to the reader."""

import httpx
import pytest

from autora_api.routers import contact

MESSAGE = {
    "name": "王小明",
    "email": "Reader@Example.com",
    "topic": "membership",
    "message": "請問月繳會員可以開發票嗎？謝謝。",
}


@pytest.fixture
async def site(api):
    contact.recent._seen.clear()
    async with httpx.AsyncClient(transport=api._transport, base_url="http://test") as client:
        yield client


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
    response = await site.post("/api/public/contact", json=MESSAGE | {"website": "http://x"})
    assert response.status_code == 202
    assert mailbox.sent == []


async def test_what_is_not_a_message_is_refused(site, mailbox):
    assert (
        await site.post("/api/public/contact", json=MESSAGE | {"email": "nope"})
    ).status_code == 422
    assert (
        await site.post("/api/public/contact", json=MESSAGE | {"message": "hi"})
    ).status_code == 422
    assert (
        await site.post("/api/public/contact", json=MESSAGE | {"topic": "x"})
    ).status_code == 422
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
