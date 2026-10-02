"""聯絡我們 (D-165): a reader writes to the site, and it reaches the operator's inbox.

The footer used to show the operator's name and address; the site now has a form instead. A
message is not stored here: it is emailed to ``CONTACT_INBOX`` (service@aisiwhale.com, which
Cloudflare forwards to the operator), with the reader's address as Reply-To, so answering it is
replying to the email. If the email cannot be sent, the reader is told so and may try again —
nothing is kept to send later.

Against spam, two things and no captcha: a field people never see (a bot fills it in, and is
told "sent" and nothing is sent), and at most a few messages an hour from one address. The
address is held in this process's memory only, for the hour, never stored or logged — like the
beacons (D-025), the site does not keep who its readers are.
"""

from __future__ import annotations

import hashlib
import time
from collections import deque
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from autora.accounts import AccountError, normalise
from autora.infra.email import EmailError, Message
from autora.infra.settings import Settings
from autora_api.deps import EmailSender, settings_dep

SettingsDep = Annotated[Settings, Depends(settings_dep)]

router = APIRouter(prefix="/api/public/contact", tags=["public"])

Topic = Literal["membership", "content", "partnership", "other"]

TOPICS: dict[Topic, str] = {
    "membership": "會員與付款",
    "content": "報導內容與更正",
    "partnership": "合作與廣告",
    "other": "其他",
}

PER_HOUR = 5
WINDOW_SECONDS = 3600


class ContactMessage(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    email: str = Field(min_length=3, max_length=200)
    topic: Topic = "other"
    message: str = Field(min_length=10, max_length=4000)
    phone: str = Field(default="", max_length=30)
    company: str = Field(default="", max_length=100)
    """Both optional: a partner's company, a reader who would rather be called."""
    lang: Literal["zh-TW", "en"] = "zh-TW"
    website: str = ""
    """Not shown to people (D-165): filled in, it was a bot."""


class _RecentSenders:
    """How many messages each address sent in the last hour, in memory, by a hash of it."""

    def __init__(self) -> None:
        self._seen: dict[str, deque[float]] = {}

    def allow(self, address: str, now: float) -> bool:
        key = hashlib.sha256(address.encode()).hexdigest()
        times = self._seen.setdefault(key, deque())
        while times and now - times[0] > WINDOW_SECONDS:
            times.popleft()
        if len(times) >= PER_HOUR:
            return False
        times.append(now)
        # forget addresses that have gone quiet, so the map does not grow for ever
        if len(self._seen) > 10_000:
            self._seen = {
                k: v for k, v in self._seen.items() if v and now - v[-1] <= WINDOW_SECONDS
            }
        return True


recent = _RecentSenders()


def _client_address(request: Request) -> str:
    """The reader's address as the proxy in front (Cloudflare, Render) saw it."""
    forwarded = request.headers.get("cf-connecting-ip") or request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _text(body: ContactMessage, email: str) -> str:
    return "\n".join(
        [
            "艾矽鯨網站「聯絡我們」有一則新留言。直接回覆這封信，就是回覆給留言的人。",
            "",
            f"姓名：{body.name.strip()}",
            f"Email：{email}",
            *([f"電話：{body.phone.strip()}"] if body.phone.strip() else []),
            *([f"公司：{body.company.strip()}"] if body.company.strip() else []),
            f"類別：{TOPICS[body.topic]}",
            f"網站語言：{body.lang}",
            "",
            "內容：",
            body.message.strip(),
        ]
    )


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def send_message(
    body: ContactMessage, request: Request, settings: SettingsDep, sender: EmailSender
) -> Response:
    if body.website.strip():
        return Response(status_code=status.HTTP_202_ACCEPTED)  # a bot: nothing is sent
    try:
        email = normalise(body.email)
    except AccountError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "not an email address") from exc
    if not recent.allow(_client_address(request), time.monotonic()):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "too many messages; try later")
    name = " ".join(body.name.split())[:40]
    message = Message(
        to=settings.contact_inbox,
        subject=f"【聯絡我們】{TOPICS[body.topic]}：{name}",
        text=_text(body, email),
        reply_to=email,
    )
    try:
        await sender.send(message)
    except EmailError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "the message could not be sent") from exc
    return Response(status_code=status.HTTP_202_ACCEPTED)
