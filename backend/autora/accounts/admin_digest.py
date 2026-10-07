"""Every morning of a shift, what waits for a person to decide (AD-10, D-234).

The ``admin.approvals_digest`` schedule (migration 0080; 15:05 in Taipei, when the worker comes in)
writes one email to each admin whose role decides approvals (owners — ADMIN_EMAILS and those let
in as owner — and editors), with a proven address, who has not turned it off (``admin_prefs``):
how many approvals wait in each company, the oldest first, which run out soon, and the link to
the inbox. Nothing waiting: no email. The back office's bell shows the same as it happens; this
is for whoever is not looking.

Here, not in a domain: it reads admins' addresses, which only the accounts layer may (D-025).
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from autora.accounts.credentials import email_verified
from autora.accounts.models import Reader
from autora.db.models import (
    DIGEST_ROLES,
    AdminPref,
    AdminRole,
    Approval,
    ApprovalState,
    Company,
    Schedule,
)
from autora.infra.email import Message, Sender

log = logging.getLogger(__name__)

DIGEST_SCHEDULE = "admin.approvals_digest"
SOON = timedelta(hours=2)
"""An approval that runs out sooner than this is called out."""
LISTED = 10
"""Per company; the rest are counted."""


@dataclass(frozen=True)
class Waiting:
    company: Company
    approvals: list[Approval]


async def recipients(session: AsyncSession, admin_emails: Iterable[str]) -> list[str]:
    """The addresses the digest goes to: proven, deciding, and not turned off."""
    owners = set(admin_emails)
    readers = (
        list((await session.scalars(select(Reader).where(Reader.email.in_(owners)))).all())
        if owners
        else []
    )
    given = (
        (
            await session.execute(
                select(Reader)
                .join(AdminRole, AdminRole.reader_id == Reader.id)
                .where(AdminRole.role.in_(DIGEST_ROLES))
            )
        )
        .scalars()
        .all()
    )
    off = set(
        (
            await session.scalars(
                select(AdminPref.reader_id).where(AdminPref.approvals_digest.is_(False))
            )
        ).all()
    )
    out: dict[str, Reader] = {}
    for reader in [*readers, *given]:
        if reader.id in off or reader.email in out:
            continue
        if await email_verified(session, reader):
            out[reader.email] = reader
    return sorted(out)


async def waiting(session: AsyncSession) -> list[Waiting]:
    """Each company's pending approvals, oldest first; companies with none left out."""
    rows = (
        await session.execute(
            select(Approval, Company)
            .join(Company, Company.id == Approval.company_id)
            .where(Approval.state == ApprovalState.PENDING)
            .order_by(Company.created_at, Approval.created_at, Approval.id)
        )
    ).all()
    by: dict = {}
    for approval, company in rows:
        by.setdefault(company.id, Waiting(company, []))
        by[company.id].approvals.append(approval)
    return list(by.values())


def _hours(delta: timedelta) -> str:
    hours = delta.total_seconds() / 3600
    if hours < 1:
        return f"{max(1, round(hours * 60))} 分鐘"
    if hours < 48:
        return f"{round(hours)} 小時"
    return f"{round(hours / 24)} 天"


def compose(to: str, groups: list[Waiting], site_base_url: str, now: datetime) -> Message:
    total = sum(len(g.approvals) for g in groups)
    soon = sum(
        1 for g in groups for a in g.approvals if a.expires_at and a.expires_at - now <= SOON
    )
    subject = f"【艾矽鯨後台】{total} 件等待審批" + (f"（{soon} 件 2 小時內到期）" if soon else "")
    lines = [f"目前有 {total} 件等待你決定。", ""]
    for group in groups:
        link = f"{site_base_url.rstrip('/')}/admin/approvals?company={group.company.id}"
        lines.append(f"■ {group.company.name}：{len(group.approvals)} 件")
        for approval in group.approvals[:LISTED]:
            note = f"已等 {_hours(now - approval.created_at)}"
            if approval.expires_at:
                left = approval.expires_at - now
                note += (
                    "，已到期"
                    if left <= timedelta(0)
                    else f"，{_hours(left)}後到期" + ("（快到了）" if left <= SOON else "")
                )
            lines.append(f"・{approval.summary}（{note}）")
        if len(group.approvals) > LISTED:
            lines.append(f"・……還有 {len(group.approvals) - LISTED} 件")
        lines.append(f"打開收件匣：{link}")
        lines.append("")
    lines.append("不想每天收到這封信：在後台右上角的鈴鐺裡關掉「每日 email 摘要」。")
    return Message(to=to, subject=subject, text="\n".join(lines))


async def send_digest(
    session: AsyncSession,
    sender: Sender,
    *,
    admin_emails: Iterable[str],
    site_base_url: str,
    now: datetime,
) -> int:
    """Send today's digest; how many were sent (0 when nothing waits or nobody gets it)."""
    groups = await waiting(session)
    if not groups:
        return 0
    sent = 0
    for address in await recipients(session, admin_emails):
        try:
            await sender.send(compose(address, groups, site_base_url, now))
            sent += 1
        except Exception:  # noqa: BLE001 - one address that bounces does not stop the others
            log.exception("approvals digest: could not send to one admin")
    return sent


def schedule_handler(settings_of: Callable, sender_of: Callable[[], Sender]):
    """The ``admin.approvals_digest`` handler."""

    async def handler(session: AsyncSession, schedule: Schedule, scheduled_for: datetime) -> None:
        settings = settings_of()
        sent = await send_digest(
            session,
            sender_of(),
            admin_emails=settings.admin_emails,
            site_base_url=settings.site_base_url,
            # now, not when it was due: a shift that starts late still counts the waiting right
            now=datetime.now(UTC),
        )
        log.info("approvals digest: %d sent", sent)

    return handler
