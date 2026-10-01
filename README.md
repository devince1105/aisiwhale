# AiSiWhale 艾矽鯨

An AI-run bilingual (Traditional Chinese / English) finance newsroom for `aisiwhale.com` (not yet
public), built on **Autora** — an AI Autonomous Company platform.
First business domain: **AI Bilingual Newsroom**. First visible surface: **3D AI Office**.

The repository is `devince1105/aisiwhale` (renamed from `autora`, 2026-10-01). Inside the code the
platform keeps its name: the Python package `autora`, the `AUTORA_*` settings, the `autora` database.

Design documents live in [`logs/`](logs/README.md). Decisions in [`logs/DECISIONS.md`](logs/DECISIONS.md).
Deployment plan: [`logs/platform/17_DEPLOYMENT.md`](logs/platform/17_DEPLOYMENT.md).

## Layout

```
backend/                 Python (one project: pyproject.toml, alembic.ini)
  autora/                the package: runtime / company / realtime / domains / db / infra
  tests/                 pytest suite (runs against a real Postgres)
  api/                   FastAPI entry point (thin: routing, auth, error format)
  worker/                worker entry point (scheduler, dispatcher, task loop)
  scripts/               tooling, e.g. gen_event_schema.py, brand_logos.py, blobs_to_r2.py
frontend/
  web/                   Next.js (admin console, 3D office, public site)
  event-schema/          generated TS types + zod for events (source of truth: backend pydantic)
infra/                   docker-compose, Dockerfiles
logs/                    architecture, decisions, development log (devlog/)
render.yaml              Render Blueprint: the API and the worker (production)
```

Dependency rule inside `backend/autora`: `runtime` → nothing above it; `company` → `runtime`;
`domains/*` → `runtime`, `company`; only `autora/app.py` imports everything (checked by import-linter).
The frontend talks to the backend only through the REST API, the WebSocket and `frontend/event-schema`.

## Prerequisites

- Python 3.12 (`python3.12` on PATH, or `make PYTHON=/path/to/python3.12 setup`)
- Node 22 + pnpm 9 (`.nvmrc` provided)
- Docker with Compose v2

## Quick start

```bash
git clone https://github.com/devince1105/aisiwhale.git
cd aisiwhale
make setup   # venv + pip install -e backend[dev] + pnpm install + .env
make dev     # start Postgres 18 (pgvector) on localhost:5434
make test    # pytest + vitest
```

Full stack in Docker: `make up` (api :8000, web :3000). Stop: `make down`.

Run API locally: `.venv/bin/uvicorn --app-dir backend/api main:app --reload`
Run worker locally: `.venv/bin/python backend/worker/main.py`

## Production

| Part | Where |
|---|---|
| Site and admin (Next.js) | Vercel — `aisiwhale.com` |
| API and worker | Render, Singapore (`render.yaml`) — `api.aisiwhale.com` |
| Postgres 18 + pgvector | Neon, Singapore |
| DNS, cover images, private blobs | Cloudflare (R2) — `img.aisiwhale.com` |

Settings are environment variables (see [`.env.example`](.env.example)); secrets live in the
Render and Vercel dashboards, never in the repository.
