# DijiAtWork — module foundation (Stage B1)

**Status:** foundation only. There is no attendance data, employee linking,
administration or database yet.

| Component | Location | Local |
|---|---|---|
| Backend | `apps/atwork-api` | FastAPI, port 8009, `/api/atwork` |
| Frontend | `apps/atwork-web` | Next.js zone, port 3005, base path `/atwork` |

## Backend routes

| Route | Access | Purpose |
|---|---|---|
| `GET /health`, `GET /health/deep` | Public | Liveness and readiness |
| `GET /api/atwork/metadata` | Public | Module identity |
| `GET /api/atwork/summary` | Public | DijiOne Home status card |
| `GET /api/atwork/me` | Bearer token | Caller identity, role and permissions from verified claims |

A valid token without a DijiAtWork role receives `module_access: false` and no
permissions. Outside development, the service refuses to start with the default
secrets.

## Frontend pages

`/` (landing) plus placeholders at `/today`, `/history` and `/admin`. The
Administration area is shown only with `atwork.overview.read`; `atwork-api` will
enforce that permission when administrative endpoints exist.

## Not registered yet

Stage B2 registers the module with the platform: permission catalog, module
registry row, gateway rewrites, Home card, `dev-all`, root workspace, CI and the
independence guard. Until then, no user holds a DijiAtWork role, so every
signed-in user sees the "No DijiAtWork access" state.
