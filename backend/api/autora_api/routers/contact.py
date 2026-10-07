"""聯絡我們 (D-165): a reader writes to the site, and it reaches the operator's inbox.

The footer used to show the operator's name and address; the site now has a form instead. A
message is not stored here: it is emailed to ``CONTACT_INBOX`` (service@aisiwhale.com, which
Cloudflare forwards to the operator), with the reader's address as Reply-To, so answering it is
replying to the email. If the email cannot be sent, the reader is told so and may try again —
nothing is kept to send later. The recipient is fixed: the form cannot be used to email anyone
else.

Against spam and floods (D-166), in this order, cheapest first:

1. a field people never see — a bot that fills it in is told "sent", and nothing is sent;
2. a form sent within seconds of opening it — a script, not a person; told "sent" likewise;
3. Cloudflare Turnstile, once ``TURNSTILE_SECRET_KEY`` is set: each message carries a one-time
   token the browser earned, checked with Cloudflare here. Changing IP address does not help a
   bot: every message needs its own token;
4. at most a few messages an hour from one address (held in this process's memory, as a hash,
   for the hour; never stored or logged — like the beacons, D-025, the site keeps no record of
   who its readers are);
5. at most ``CONTACT_DAILY_CAP`` messages a day from everyone together. The form sends through
   the same Resend account as the sign-in links, and that account has a daily quota: a flood
   that got through everything above still cannot use it up and lock readers — and the
   operator — out of signing in.
"""

from __future__ import annotations

import hashlib
import logging
import time
from collections import deque
from datetime import UTC, date, datetime
from typing import Annotated, Literal, Protocol

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from autora.accounts import AccountError, normalise
from autora.infra.email import EmailError, Message
from autora.infra.settings import Settings
from autora_api.deps import EmailSender, settings_dep
from autora_api.live import LIVE

log = logging.getLogger(__name__)

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
MIN_FILL_MS = 3000
"""Faster than this from opening the form to sending it, and it was not a person typing."""

TURNSTILE_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


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
    elapsed_ms: int = Field(default=0, ge=0)
    """How long the form was open before it was sent (D-166)."""
    turnstile_token: str = Field(default="", max_length=4096)
    """Cloudflare Turnstile's one-time token for this message (D-166)."""


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


class _DailyCap:
    """How many messages went out today (UTC), all senders together."""

    def __init__(self) -> None:
        self.day: date | None = None
        self.sent = 0

    def allow(self, today: date, cap: int) -> bool:
        if today != self.day:
            self.day, self.sent = today, 0
        if self.sent >= cap:
            return False
        self.sent += 1
        return True


recent = _RecentSenders()
daily = _DailyCap()


class TurnstileVerifier(Protocol):
    async def __call__(self, secret: str, token: str, address: str) -> bool: ...


async def cloudflare_verifies(secret: str, token: str, address: str) -> bool:
    """Ask Cloudflare whether the token is genuine, unused and recent. Unreachable is a no."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                TURNSTILE_URL, data={"secret": secret, "response": token, "remoteip": address}
            )
        answer = response.json()
    except (httpx.HTTPError, ValueError):
        log.warning("Turnstile could not be reached", exc_info=True)
        return False
    if not answer.get("success"):
        log.info("Turnstile refused a token: %s", answer.get("error-codes"))
    return bool(answer.get("success"))


def turnstile_dep() -> TurnstileVerifier:
    """Cloudflare's own check. Tests override it."""
    return cloudflare_verifies


Turnstile = Annotated[TurnstileVerifier, Depends(turnstile_dep)]


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
    body: ContactMessage,
    request: Request,
    settings: SettingsDep,
    sender: EmailSender,
    turnstile: Turnstile,
) -> Response:
    # 1, 2: a bot is told it worked, so it learns nothing to try differently
    if body.website.strip() or body.elapsed_ms < MIN_FILL_MS:
        return Response(status_code=status.HTTP_202_ACCEPTED)
    try:
        email = normalise(body.email)
    except AccountError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "not an email address") from exc
    address = _client_address(request)
    # 3: one token per message, checked with Cloudflare
    secret = settings.turnstile_secret_key
    if secret is not None and not (
        body.turnstile_token
        and await turnstile(secret.get_secret_value(), body.turnstile_token, address)
    ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "the check that you are a person failed")
    # 4, 5: one address, then everyone
    if not recent.allow(address, time.monotonic()):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "too many messages; try later")
    cap = LIVE.value(settings, "contact.daily_cap")  # the back office may change it (AD-11)
    if not daily.allow(datetime.now(UTC).date(), cap):
        log.warning("聯絡我們: today's cap of %d messages reached", cap)
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "too many messages today")
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
