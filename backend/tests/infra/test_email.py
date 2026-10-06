"""The Resend sender: what it sends, and that a refusal says why (D-043)."""

import json
import logging

import httpx
import pytest

from autora.infra.email import RESEND_URL, EmailError, Message, ResendSender

MESSAGE = Message(to="reader@example.com", subject="你的登入連結", text="點下面的連結")


def _sender(status: int, body: dict, seen: list) -> ResendSender:
    def answer(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(status, json=body)

    return ResendSender(
        api_key="re_test",
        sender="Autora <service@nanguado.com>",
        client=httpx.AsyncClient(transport=httpx.MockTransport(answer)),
    )


async def test_it_sends_what_resend_expects():
    seen: list[httpx.Request] = []
    await _sender(200, {"id": "e1"}, seen).send(MESSAGE)
    [request] = seen
    assert str(request.url) == RESEND_URL
    assert request.headers["Authorization"] == "Bearer re_test"
    assert json.loads(request.content) == {
        "from": "Autora <service@nanguado.com>",
        "to": ["reader@example.com"],
        "subject": "你的登入連結",
        "text": "點下面的連結",
    }


async def test_a_reply_goes_where_the_message_says(caplog):
    # D-165: a reader's message to the site is answered to the reader, not to the site
    seen: list[httpx.Request] = []
    message = Message(to="service@aisiwhale.com", subject="s", text="t", reply_to="r@example.com")
    await _sender(200, {"id": "e2"}, seen).send(message)
    assert json.loads(seen[0].content)["reply_to"] == "r@example.com"


async def test_a_refusal_says_why_in_the_error_and_the_server_log(caplog):
    """The first real send failed with only "(403)" to go on; Resend had said why."""
    reason = "The nanguado.com domain is not verified. Please, add and verify your domain"
    sender = _sender(403, {"statusCode": 403, "name": "validation_error", "message": reason}, [])
    with caplog.at_level(logging.WARNING), pytest.raises(EmailError, match="not verified"):
        await sender.send(MESSAGE)
    assert reason in caplog.text


def test_an_account_email_says_whose_it_is():
    """D-043: a link from nobody-in-particular looks like phishing (D-230: the emails a reader
    gets now are a confirmation, a reset and a note that their address was registered again)."""
    from autora.accounts import emails

    for message in (
        emails.verify_email("reader@example.com", "https://aisiwhale.com/x"),
        emails.reset_email("reader@example.com", "https://aisiwhale.com/x"),
        emails.account_exists_email("reader@example.com", "https://aisiwhale.com"),
    ):
        assert message.subject.startswith("艾矽鯨")
        assert "艾矽鯨" in message.text and "艾矽鯨" in (message.html or "")
