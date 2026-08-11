# DijiOne

**DijiOne** — the unified digital operating workspace for Dijital Team.
First major module: **DijiTalentFlow**.

This is a modular-monolith MVP: one Next.js 16 App Router frontend
(`apps/web`) and one FastAPI backend (`apps/api`), sharing one sign-in
experience, one design system, and one platform API.

## Quick start

See [`docs/setup.md`](docs/setup.md) for full instructions. Short version:

```bash
# Backend
cd apps/api
py -3.12 -m venv .venv
./.venv/Scripts/python.exe -m pip install -r requirements.txt
./.venv/Scripts/python.exe -m alembic upgrade head
./.venv/Scripts/python.exe scripts/seed.py --reset
./.venv/Scripts/python.exe -m uvicorn app.main:app --port 8000 --reload

# Frontend (separate terminal)
cd apps/web
npm install
npm run dev
```

Open the frontend URL Next.js prints (usually `http://localhost:3000`) and
sign in via the Dev Identity Mode persona switcher — no credentials
required locally (see `docs/platform/authentication.md`).

## Documentation

| Doc | Contents |
|---|---|
| [`PLAN.md`](PLAN.md) | Build plan, phases, architecture decisions |
| [`docs/mvp-status.md`](docs/mvp-status.md) | What's done vs. deferred |
| [`docs/setup.md`](docs/setup.md) | Full local setup |
| [`docs/api.md`](docs/api.md) | REST API reference |
| [`docs/platform/architecture.md`](docs/platform/architecture.md) | Platform architecture |
| [`docs/platform/authentication.md`](docs/platform/authentication.md) | Auth/RBAC, Dev Identity Mode |
| [`docs/platform/design-system.md`](docs/platform/design-system.md) | Brand tokens, components |
| [`docs/platform/module-framework.md`](docs/platform/module-framework.md) | How modules plug into DijiOne |
| [`docs/platform/copilot.md`](docs/platform/copilot.md) | Future Copilot/Cowork architecture |
| [`docs/talent-flow/requirements.md`](docs/talent-flow/requirements.md) | DijiTalentFlow requirements & status |
| [`docs/talent-flow/data-model.md`](docs/talent-flow/data-model.md) | Domain model, tenant isolation |
| [`docs/talent-flow/workflows.md`](docs/talent-flow/workflows.md) | Request lifecycle, notifications, audit |
| [`docs/integrations/lever.md`](docs/integrations/lever.md) | Lever provider architecture |
| [`docs/integrations/hubspot.md`](docs/integrations/hubspot.md) | HubSpot provider architecture |

## Repository layout

```text
dijione-platform/
├── apps/
│   ├── web/     # Next.js 16 App Router — DijiOne shell + DijiTalentFlow UI
│   └── api/     # FastAPI — platform + module API, SQLAlchemy 2, Alembic
├── docs/         # Architecture, requirements, workflows, API reference
├── PLAN.md
├── CLAUDE.md      # Authoritative product/engineering contract
└── .env.example
```

## Status

First autonomous build phase complete — see
[`docs/mvp-status.md`](docs/mvp-status.md) for the full checklist against
CLAUDE.md's Definition of MVP Done.
