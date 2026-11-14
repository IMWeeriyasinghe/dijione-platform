# Diji On-site — Architecture

**Status:** approved 2026-10-22 (revision 2). Components marked *planned*
are delivered by the Phase 1 PR sequence (1.0 docs → 1.1 Workforce
Directory → 1.2 platform registration → 1.3 `onsite-api` → 1.4 deploy/CI/
boundaries → 1.5 `onsite-web` skeleton).

## Non-negotiable rules

1. Diji On-site stays an independently deployable and removable application
   module with its own API, database and UI.
2. No On-site runtime dependency on DijiBirthday, DijiTalentFlow, DijiAdmin
   or any other application module.
3. Shared dependencies only through published platform/source contracts:
   `platform-api`, the `people-api` Workforce Directory, generic shared
   auth/design-system packages, and the Azure attendance source through the
   bounded `attendance_source` adapter.
4. No changes to the Birthday employee model, sync lifecycle, endpoints or
   jobs for On-site.
5. The Workforce Directory stays a generic People capability: no
   On-site-specific fields, routes, naming or business rules.
6. Generic platform/auth behaviour belongs in shared packages; On-site
   scope interpretation, DTOs and application logic stay inside the module.
7. The module-removal test (`docs/onsite/module-removal.md`) is a required
   acceptance gate.
8. No other DijiOne application's migration, deployment, runtime path or
   database may require On-site to exist.

## Ownership

| Component | Owns |
|---|---|
| `onsite-api` (FastAPI, :8008, *planned*) | All On-site domain logic; the `app/attendance_source/` adapter — the **only** code allowed to reach Azure SQL `onsite.*` |
| `onsite_<env>` database (*planned*) | Raw-event mirror, site registry/settings, agent-status snapshot, sync runs. Used only by `onsite-api` |
| `onsite-web` (Next.js zone, :3004, `basePath: /onsite`, *planned*) | All On-site UI. Scope hook, constants and DTO types live in `apps/onsite-web/src/lib/` |

## Allowed dependencies

| Dependency | Contract |
|---|---|
| `platform-api` | JWT claims verified locally (`make_get_claims`); module registry and role/permission catalog as data; audit/notify via `PlatformClient` (best effort) |
| `people-api` | Workforce Directory HTTP contract only, via `auth_client_py.WorkforceDirectoryClient`. Never the People database. Used for names/departments/photos of *verified* employees (by `bamboohr_id`) and the admin directory search. If unreachable, verified attendance stays attributed without names; mapping changes are refused (503) |
| Shared packages | `auth-client-py`, `auth-client-ts` (generic `useAuth`/`request`), `design-system` |
| Azure SQL `onsite.*` | SELECT-only, only through `onsite-api/app/attendance_source/` |

**Forbidden:** On-site → any other application service (code, HTTP, URL
setting or database); On-site → `people_<env>` or any database other than
`onsite_<env>`; any application → `onsite-api`, `onsite_<env>` or Azure SQL
`onsite.*`; any On-site-specific code in `people-api`.

**Registration points** (data/config only, inert when On-site is absent):
`platform-api` catalog + `application_modules` row (removal = disable the
row, never a migration revert); `shell-web` rewrites (`/onsite`,
`/onsite/:path*`, `/api/onsite/:path*`) and `ModuleCard` summary path;
`deploy/`, `.github/workflows/`, `scripts/dev-all.js`, root workspaces,
`docs/`.

## Dependency diagram

```
┌─────────────────────── APPLICATION MODULES ── each owns its DB + UI ───────────────────────┐
│  DijiTalentFlow        DijiBirthday             DijiAdmin           Diji On-site (planned)   │
│  talent-api            birthday-api             admin-api (no DB)   onsite-api               │
│  talent_<env>          birthday_<env>           admin-web           onsite_<env>             │
│  talent-web            birthday-web                                 onsite-web               │
│  talentflow-portal-web birthday-supplier-web                        └ attendance_source ─────┼─► Azure SQL onsite.*
│                                                                                              │   SELECT-only (MI token)
│  pre-existing: admin-api ─read-only─► talent-api    On-site adds NO edges to/from modules    │
└──────────┬──────────────────────┬──────────────────────┬──────────────────────┬─────────────┘
           │ published contracts only: HTTP + signed JWT claims + shared packages
           ▼                      ▼                      ▼                      ▼
┌──────────────────────── PLATFORM CORE + SOURCE DOMAINS (shared) ────────────────────────────┐
│  platform-api     identity · claims · RBAC catalog · module registry · audit/notify          │
│  recruitment-api  Lever                                    ◄── DijiTalentFlow                │
│  people-api       BambooHR (sole owner)                                                      │
│                    ├─ Employee contract  /api/people/employees      UNCHANGED ◄── DijiBirthday│
│                    └─ Workforce Directory /api/people/workforce-directory  NEW ◄── Diji On-site│
│  packages         auth-client-py · auth-client-ts · design-system · contracts                │
└──────────────────────────────────────────────────────────────────────────────────────────────┘
shell-web gateway: routing registration per module; a missing module's routes fail alone.
```

## Data flow

```
Diji On-site Attendance (Azure SQL sql-diji-onsite-attendance / sqldb-diji-onsite-attendance)
   │   onsite.Sites · onsite.AttendanceEvents · onsite.AgentStatus — ONE authoritative source shared by
   │   DijiOne DEV, UAT and PROD; written only by its ingestion service (Diji On-site Agent -> HTTPS)
   │ SELECT-only · Entra token from onsite-api's system-assigned managed identity (one user per environment)
   ▼                                   [ingestion API: separate plane, unchanged, not used]
onsite-api/app/attendance_source/      incremental mirror: EventId insert-if-absent,
   │                                   ReceivedUtc high-water mark with a 10-minute overlap
   ▼
onsite_<env>                           raw columns verbatim + derived site_local_date
   │                                     ◄── people-api Workforce Directory (HTTP, TTL cache)
   ▼
On-site domain services                summaries computed on read · ZKBioTime ID → verified mapping (dated) → bamboohr_id
   ▼
/api/onsite/*                          claims → permissions + enabled-site allow-list
   ▼
onsite-web (/onsite via shell-web)
```

## Key design decisions

- **One source, one mirror per environment.** Diji On-site Attendance is the
  single authoritative attendance store; DEV, UAT and PROD each keep their own
  derived `onsite_<env>` mirror of the same facts and can never write the source.
  Dashboards read only `onsite_<env>`; Azure SQL is touched only by the sync
  (scheduled Container Apps Job + authorized "Sync now"), following the
  CLAUDE.md source-synchronization lifecycle (rules 10–18). A failed sync
  keeps the last good mirror and the UI shows "Source unavailable" rather
  than reporting absence.
- **No Azure schema changes.** Only a contained, SELECT-only database user
  for `onsite-api`'s managed identity (column-level on `onsite.Sites`,
  excluding `ApiKeyHash`).
- **Site allow-list fails closed.** `site_settings.enabled` defaults to
  false; every repository read requires `allowed_site_ids`; an unknown or
  disabled site returns 404. No site id is hardcoded.
- **Summaries on read.** Daily first/latest activity and punch counts are
  computed by `GROUP BY site_id, site_local_date, emp_code`; nothing derived
  is persisted in V1.
- **Refresh.** Near-real-time: the mirror syncs every minute
  (`onsite-sync-job`, `* * * * *`) and dashboards refetch every 30 s
  (TanStack Query) against `onsite-api` only; no websockets/SSE. Expected
  punch-to-dashboard delay ~1–2 minutes. See `deployment.md` "Refresh
  cadence".

## Removal

See `docs/onsite/module-removal.md`.
