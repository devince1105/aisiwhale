"""Who did what in the back office (AD-06, D-234): every change that comes through its door.

``require_operator`` marks a request that changes something (not GET/HEAD/OPTIONS) with the
actor it let in; ``AuditMiddleware`` writes one ``admin_actions`` row for it when the response
starts — the route's template and name, the ids in its path, the company it concerns, what was
sent (secrets masked, long text cut), the status, the caller's address. Refused attempts are
written too (a 409, a 422): the record is of what people tried, not only of what happened.

Doing it here, not in each handler, is the point: a route added tomorrow is recorded without
anybody remembering to, and test_admin_audit.py fails if a write route bypasses the door.

The row is written before the response goes out, so the caller's next request sees it. If
writing it fails, the failure is logged and the response is still sent — the change itself is
already committed by then, and refusing it now would only misreport what happened.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from typing import Any
from urllib.parse import parse_qsl

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from autora.db.models import AdminAction, Agent, Approval, Company, Project, WorkflowRun
from autora.domains.newsroom.models import Article, Source, Story
from autora.runtime.actor import Actor

log = logging.getLogger(__name__)

READ_ONLY = frozenset({"GET", "HEAD", "OPTIONS"})
_ACTOR = "audit_actor"

MAX_BODY = 64 * 1024
"""More than this is not kept, only its size."""
MAX_TEXT = 2000
MAX_INPUT = 16 * 1024
SECRET = re.compile(r"pass|token|secret|authorization|cookie|api_key", re.IGNORECASE)

# a target's company, for the ids a route names
_OWNERS: dict[str, Any] = {
    "article": Article,
    "story": Story,
    "approval": Approval,
    "agent": Agent,
    "project": Project,
    "source": Source,
    "run": WorkflowRun,
}


def mark(request: Request, actor: Actor) -> None:
    """``require_operator`` let ``actor`` in to change something: record the request."""
    if request.method not in READ_ONLY:
        setattr(request.state, _ACTOR, actor.model_dump(mode="json"))


def _masked(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: "***" if SECRET.search(str(k)) else _masked(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_masked(v) for v in value]
    if isinstance(value, str) and len(value) > MAX_TEXT:
        return value[:MAX_TEXT] + f"…（共 {len(value)} 字）"
    return value


def _input(scope: Scope, body: bytes, overflow: bool) -> dict[str, Any]:
    query = dict(parse_qsl((scope.get("query_string") or b"").decode("latin-1")))
    out: dict[str, Any] = {}
    if query:
        out["query"] = _masked(query)
    if overflow:
        out["body"] = f"（{len(body)} 位元組以上，未保存）"
    elif body:
        try:
            out["body"] = _masked(json.loads(body))
        except (ValueError, UnicodeDecodeError):
            out["body"] = f"（{len(body)} 位元組，不是 JSON）"
    if len(json.dumps(out, ensure_ascii=False)) > MAX_INPUT:
        keys = sorted(out.get("body", {}).keys()) if isinstance(out.get("body"), dict) else []
        out = {
            "truncated": True,
            "body_keys": keys,
            **({"query": out["query"]} if "query" in out else {}),
        }
    return out


def _uuid(value: Any) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError):
        return None


async def _company(
    session: AsyncSession,
    path: dict[str, Any],
    given: dict[str, Any],
    target: tuple[str | None, str | None],
) -> uuid.UUID | None:
    """The company a change concerns: named by the route or the request, else its target's."""
    for source in (
        path,
        given.get("query", {}),
        given.get("body", {}) if isinstance(given.get("body"), dict) else {},
    ):
        if (found := _uuid(source.get("company_id"))) is not None:
            return found
    slug = given.get("query", {}).get("company") or (
        given.get("body", {}).get("company") if isinstance(given.get("body"), dict) else None
    )
    if isinstance(slug, str) and slug:
        return await session.scalar(select(Company.id).where(Company.slug == slug))
    kind, ident = target
    model = _OWNERS.get(kind or "")
    if model is not None and (key := _uuid(ident)) is not None:
        return await session.scalar(select(model.company_id).where(model.id == key))
    return None


def _target(path: dict[str, Any]) -> tuple[str | None, str | None]:
    """The route's first id other than the company's: ``{article_id}`` → ("article", id)."""
    for name, value in path.items():
        if name.endswith("_id") and name != "company_id":
            return name[: -len("_id")], str(value)
    if "company_id" in path:
        return "company", str(path["company_id"])
    return None, None


def client_ip(scope: Scope) -> str | None:
    for key, value in scope.get("headers", []):
        if key == b"cf-connecting-ip" and value.strip():
            return value.decode("latin-1").strip()
    client = scope.get("client")
    return client[0] if client else None


async def _record(scope: Scope, status: int, body: bytes, overflow: bool) -> None:
    actor = (scope.get("state") or {}).get(_ACTOR)
    if actor is None:
        return
    route = scope.get("route")
    path = dict(scope.get("path_params") or {})
    given = _input(scope, body, overflow)
    target = _target(path)
    # the app's own session (tests share theirs through the same override)
    from autora_api.deps import get_session

    app = scope["app"]
    factory = app.dependency_overrides.get(get_session, get_session)
    sessions = factory()
    session: AsyncSession = await anext(sessions)
    try:
        session.add(
            AdminAction(
                actor=actor,
                method=scope["method"],
                route=getattr(route, "path", scope.get("path", "")),
                action=getattr(route, "name", None) or scope.get("path", ""),
                target_type=target[0],
                target_id=target[1],
                company_id=await _company(session, path, given, target),
                status=status,
                input=given,
                ip=client_ip(scope),
            )
        )
        await session.commit()
    finally:
        await sessions.aclose()


class AuditMiddleware:
    """Pure ASGI: tees the request body as the app reads it, and records when the response
    starts (or when the app fails without one: a 500)."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] in READ_ONLY:
            await self.app(scope, receive, send)
            return
        body = bytearray()
        overflow = False
        recorded = False

        async def tee() -> Message:
            nonlocal overflow
            message = await receive()
            if message["type"] == "http.request" and not overflow:
                chunk = message.get("body", b"")
                if len(body) + len(chunk) > MAX_BODY:
                    overflow = True
                else:
                    body.extend(chunk)
            return message

        async def safely(status: int) -> None:
            nonlocal recorded
            if recorded:
                return
            recorded = True
            try:
                await _record(scope, status, bytes(body), overflow)
            except Exception:  # noqa: BLE001 - never turn a done change into an error
                log.exception(
                    "admin audit: could not record %s %s", scope["method"], scope.get("path")
                )

        async def audited(message: Message) -> None:
            if message["type"] == "http.response.start":
                await safely(message["status"])
            await send(message)

        try:
            await self.app(scope, tee, audited)
        except Exception:
            await safely(500)
            raise
