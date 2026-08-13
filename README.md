# DijiOne

**DijiOne** — the unified digital operating workspace for Dijital Team.
First major module: **DijiTalentFlow**.

Since Phase 2.5, DijiOne is an application-level service-oriented
platform: three Next.js frontend apps behind a gateway, five FastAPI
backend services, each independently runnable and each owning its own
data. See [`docs/platform/service-architecture.md`](docs/platform/service-architecture.md)
for the full picture.

## Quick start

See [`docs/platform/local-development.md`](docs/platform/local-development.md)
for full instructions. Short version:

```bash
npm install
npm run dev:all
```

Open `http://localhost:3000` and sign in via the Dev Identity Mode persona
switcher — no credentials required locally (see
[`docs/platform/authentication.md`](docs/platform/authentication.md)).

## Documentation

| Doc | Contents |
|---|---|
| [`PLAN.md`](PLAN.md) | Build plan, phases, architecture decisions |
| [`docs/mvp-status.md`](docs/mvp-status.md) | What's done vs. deferred |
| [`docs/platform/local-development.md`](docs/platform/local-development.md) | Full local setup, all 8 services |
| [`docs/platform/service-architecture.md`](docs/platform/service-architecture.md) | The 8 services, what each owns |
| [`docs/platform/service-contracts.md`](docs/platform/service-contracts.md) | API surface per service, gateway routing |
| [`docs/platform/failure-isolation.md`](docs/platform/failure-isolation.md) | What happens when one service is down |
| [`docs/platform/architecture.md`](docs/platform/architecture.md) | Platform architecture overview |
| [`docs/platform/authentication.md`](docs/platform/authentication.md) | Auth/RBAC, Dev Identity Mode |
| [`docs/platform/authorization.md`](docs/platform/authorization.md) | Authorization engine, claims-based auth |
| [`docs/platform/admin-center.md`](docs/platform/admin-center.md) | DijiOne Admin Center |
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
│   ├── shell-web/       # Next.js — DijiOne Home, gateway (port 3000)
│   ├── admin-web/       # Next.js — Admin Center pages (port 3001)
│   ├── talent-web/      # Next.js — DijiTalentFlow pages (port 3002)
│   ├── platform-api/    # FastAPI — identity, authZ, registry, audit (port 8000)
│   ├── admin-api/       # FastAPI — admin business rules, no database (port 8001)
│   ├── talent-api/      # FastAPI — DijiTalentFlow's own data (port 8002)
│   ├── birthday-api/    # FastAPI — skeleton (port 8003)
│   └── spark-api/       # FastAPI — skeleton (port 8004)
├── packages/
│   ├── design-system/    # Shared UI primitives + shell chrome (TS)
│   ├── auth-client-ts/   # Shared frontend session/auth logic (TS)
│   ├── auth-client-py/   # Shared claims verification + Platform Core client (Python)
│   └── contracts/         # Shared TS types
├── docs/         # Architecture, requirements, workflows, API reference
├── PLAN.md
├── CLAUDE.md      # Authoritative product/engineering contract
└── package.json   # npm workspace root — npm run dev:all
```

## Status

Phase 1 (MVP), Phase 2 (Identity/Authorization/Admin Center), and Phase 2.5
(Application-Level Service Separation) complete — see
[`docs/mvp-status.md`](docs/mvp-status.md) for the full checklist against
CLAUDE.md's Definition of MVP Done.
