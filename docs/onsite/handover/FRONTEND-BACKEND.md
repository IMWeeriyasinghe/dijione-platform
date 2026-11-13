# Frontend and backend implementation

## onsite-api (`apps/onsite-api`, FastAPI, Python 3.12, port 8008 locally)

Layers: `app/api/routes` → `app/services` → `app/repositories` → `app/models`; Azure SQL only in
`app/attendance_source/` (`sql_client.py` pyodbc + ODBC Driver 18 + managed-identity token; `mock_client.py`
for tests/local; `INTEGRATIONS_MODE` = `live` | `mock` | `none`).

### Routes (all under `/api/onsite`)
| Route | Permission | Notes |
|---|---|---|
| `GET /metadata`, `/me`, `/summary`, `/freshness` | `/me` any On-site role; others dashboard read | `/me` drives UI permission gating |
| `GET /sites` | dashboard read | enabled sites only, with site-local `today` |
| `GET /dashboard/overview`, `/hourly-activity` | dashboard read | `date` or `date_from`/`date_to` (≤ 92 days) |
| `GET /dashboard/activity-trend`, `/recent-activity` | dashboard read | |
| `GET /today` | attendance read | sort, filters, `page`/`page_size` (default 10) |
| `GET /activity` | attendance read | filters + `hour` (0–23, site-local, UTC `[start,end)` per date), `sort=-time|time` |
| `GET /employees`, `/employees/{code}` | attendance read | `summary` population tiles; detail `include_events=false` for lazy profile |
| `GET /employees/{code}/photo` | attendance read | 404 unless exactly one directory match with a photo |
| `GET /exceptions` | exceptions read | flag counts + reasons, sort |
| `GET /{today,activity,employees,exceptions,dashboard/overview}/export` | same as view | server-built .xlsx, same filters as the view |
| `POST /sync`, `GET /sync/runs/{id}`, `/sync/history` | `onsite.sync.request` / health read | |
| `POST /internal/scheduled-sync` | internal token | only the ACA job calls it |
| `GET /admin/health` | health read | feed, Agent, reconciliation |
| `GET /admin/identity-match` | identity read | `page`/`page_size`/`identity_class`/`q`; `format=csv` full |
| `GET|PUT /admin/sites[/{id}]` | `onsite.sites.manage` | enable/disable, audited to platform-api |
Health probes: `GET /health`, `/health/deep`.

Site scope: every repository read takes `allowed_site_ids` = enabled sites; unknown/disabled site → 404.

### Employee photos
Source is **BambooHR `photoUrl`**, the same proven approach as Customer Portal V2 (its `/staff/{id}/photo`
server proxy; Customer Portal V2 uses Microsoft Graph only for the signed-in user's own photo and a
directory listing, never for employee photos). **No Microsoft Graph integration exists in Diji On-site and
none is needed.** Flow: people-api sync reads `GET /employees/directory` (best-effort) → stores `photo_url`
(https only) → internal proxy `GET /api/people/workforce-directory/{bamboohr_id}/photo` (https-only redirects,
sniffed type, 2 MB cap) → onsite-api `employee_photos.py` (LRU 3,000; hit 24 h, miss 6 h, throttle =
Retry-After; single-flight; ≤ 4 concurrent) → browser (lazy, in-view, once per session). Live: 347 of 537
directory employees have photos (347/360 active). Full detail: `docs/onsite/photos-pagination-drilldown.md`.

## onsite-web (`apps/onsite-web`, Next.js 16, React 19, TanStack Query 5, Tailwind 4, port 3004, basePath `/onsite`)

Pages: `/` Overview, `/today`, `/activity`, `/employees`, `/exceptions`, `/admin/health`, `/admin/identity`,
`/admin/sites`. Navigation built from `/api/onsite/me` permissions (`onsite-shell.tsx`); mobile bottom nav
(`MobileNav.tsx`) for the five operational pages.

Shared building blocks:
| File | Role |
|---|---|
| `components/kit.tsx` | PageTop, Panel, KpiCard, InfoTip, Initials + lazy `EmployeePhoto`, Person, FilterPanel + chips, Segmented, Pager (10/20/50/100), skeletons, empty states |
| `components/DataView.tsx` | sticky sortable table ≥ 768 px, cards below (one rendered via `useMinWidth`) |
| `components/charts.tsx` | dependency-free BarChart (axes, tooltips, keyboard, selectable, scrollable) + BreakdownList |
| `components/EmployeeProfile.tsx` | profile drawer; summary first, per-day events lazily via `/activity` |
| `components/HourActivitySheet.tsx` | hour drill-down sheet |
| `components/FreshnessIndicator.tsx` | page refresh vs mirror sync vs latest event vs Agent heartbeat |
| `lib/live-refresh.ts` | `liveQuery`: refetch 30 s, visible tab only, keep previous data |
| `lib/url-state.ts` | filters/page/selection in the URL (survive refresh/back, drill-down links) |
| `lib/period.ts`, `paging.ts`, `page-size.ts`, `dialog-stack.ts`, `use-in-view.ts`, `use-media.ts` | periods (site-local), paging/clamp, size persistence (number only), Escape stacking, lazy loading, breakpoints |

Data: `lib/dashboard.ts` (typed fetchers), `lib/api.ts` (admin/sync). Only `/api/onsite`, `/api/auth`,
`/api/notifications` may be called (`__tests__/boundaries.test.ts`).

## Touch points outside the module
- **platform-api**: `onsite` registry row (ACTIVE in UAT/PROD via migration `m3n4o5p6q7r8`), roles
  `ONSITE_VIEWER` (dashboard/attendance/exceptions read) and `ONSITE_ADMIN` (+ health, identity, sync, sites).
- **shell-web**: rewrites `/onsite`, `/api/onsite/*`; Home card.
- **people-api**: generic Workforce Directory (`docs/platform/workforce-directory.md`), migration head `0004`.
- **admin-web**: role assignment UI (generic; no On-site code).

## Tests (counts on 2026-11-13, release head 7eabdc6)
onsite-api 129 · people-api 35 · auth-client-py 19 · onsite-web 68 (vitest) · tsc/eslint clean ·
module-independence guard OK. Commands: MAC-DEVELOPMENT-SETUP.md.
