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
| `GET /api/atwork/management/access` | `atwork.management.access` | Access check for the future Management area |

A valid token without a DijiAtWork role receives `module_access: false` and no
permissions. Outside development, the service refuses to start with the default
secrets.

## Frontend pages

`/` (landing) plus placeholders at `/today`, `/history` and `/management`. The
Management area is shown only with `atwork.management.access`, which `atwork-api`
also enforces.

## Platform registration

The module is registered as `COMING_SOON`. See `administration.md` for the
central and local responsibilities and `module-removal.md` for the removal gate.
