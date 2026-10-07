from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import autora
from autora.app import load_event_catalogs
from autora.db.session import dispose_engine, get_engine, get_sessionmaker
from autora.infra.settings import get_settings
from autora.realtime.gateway import EventHub
from autora_api import problems
from autora_api.audit import AuditMiddleware
from autora_api.deps import OFFICE_CALL
from autora_api.live import LIVE
from autora_api.routers import (
    admin_access,
    admin_activity,
    admin_audit,
    admin_auth,
    admin_coins,
    admin_me,
    admin_memberships,
    admin_settings,
    approval_report,
    approvals,
    auth,
    coins,
    companies,
    contact,
    cycles,
    events,
    finance,
    meta,
    newsroom,
    payments,
    projects,
    public,
    realtime,
    reporting,
    runs,
    tasks,
    team,
    watchlist,
    workflows,
    ws,
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    get_settings()  # fail fast on missing/inconsistent configuration
    # the last call, written down before this start (D-237): the deploy's migrations just woke
    # the database, so reading it costs no extra wake
    await OFFICE_CALL.recall(get_sessionmaker())
    # the settings the back office changed (AD-11), read the same once
    await LIVE.recall(get_sessionmaker())
    hub = EventHub(engine=get_engine(), session_factory=get_sessionmaker())
    app.state.hub = hub
    await hub.start()
    try:
        yield
    finally:
        await hub.stop()
        await dispose_engine()


def create_app() -> FastAPI:
    load_event_catalogs()  # stored events of every layer must be parseable
    app = FastAPI(title="Autora API", version=autora.__version__, lifespan=lifespan)
    problems.install(app)
    # The web app runs on its own origin (localhost:3000 in dev). WebSockets are not subject
    # to CORS; they authenticate with the token in the query string.
    # who did what in the back office (AD-06): inside CORS, so a refused preflight is not a change
    app.add_middleware(AuditMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=get_settings().cors_origins,
        allow_methods=["GET", "POST", "PUT", "DELETE"],  # PUT, DELETE: a reader's watchlist
        allow_headers=["Authorization", "Content-Type"],
        expose_headers=["X-Total-Count"],  # the article list's page numbers
        # the reader's session is a cookie (D-025), and a cross-origin request only carries it
        # when both sides say so; the origins above are the only ones allowed to ask
        allow_credentials=True,
    )

    @app.get("/health", tags=["meta"])
    def health() -> dict[str, str]:
        return {"status": "ok", "version": autora.__version__}

    app.include_router(companies.router)
    app.include_router(events.router)
    app.include_router(runs.router)
    app.include_router(tasks.router)
    app.include_router(approval_report.router)  # before the inbox's own routes
    app.include_router(approvals.router)
    app.include_router(workflows.router)
    app.include_router(realtime.router)
    app.include_router(reporting.router)
    app.include_router(finance.router)
    app.include_router(projects.router)
    app.include_router(cycles.router)
    app.include_router(public.router)
    app.include_router(auth.router)
    app.include_router(admin_auth.router)
    app.include_router(admin_memberships.router)
    app.include_router(admin_coins.router)
    app.include_router(admin_audit.router)
    app.include_router(admin_activity.router)
    app.include_router(admin_access.router)
    app.include_router(admin_me.router)
    app.include_router(admin_settings.router)
    app.include_router(contact.router)
    app.include_router(payments.router)
    app.include_router(watchlist.router)
    app.include_router(coins.router)
    app.include_router(newsroom.router)
    app.include_router(team.router)
    app.include_router(meta.router)
    app.include_router(ws.router)
    return app
