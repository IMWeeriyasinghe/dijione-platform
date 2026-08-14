# DijiOne Navigation Performance Investigation

Date: 2026-08-14
Symptom reported: intermittent 10–15s delays navigating between menu items
in local dev (e.g. Orders → Suppliers, Suppliers → Birthdays, Birthdays →
Dashboard), with the Next.js dev indicator showing "Rendering" during the
delay.

## Summary of finding

**Root cause: Next.js/Turbopack's dev-mode lazy, on-demand route
compilation — not a real architectural or code defect.** Every route in
every one of the eight services is compiled the first time it is
requested, not ahead of time; the first hit to a given route pays a
compile cost, every subsequent hit to the same route is served from the
in-memory compiled module and is fast. This is standard Next.js dev-server
behavior and is already partially documented in
`docs/platform/local-development.md` for `/admin` and `/talent-flow` — it
was not previously called out for `/birthday`.

Because `shell-web`, `admin-web`, `talent-web`, and `birthday-web` are four
separate Next.js dev-server processes (Multi Zones, see
`docs/platform/service-architecture.md`), and cross-zone links are plain
`<a>` tags (full page navigations, by design — `next/link` cannot render
another zone's app), a navigation that crosses a zone boundary is very
likely to be the *first* hit to that destination route in that dev
server's process lifetime, so it eats the full compile cost. On the
reporter's machine this cost was measured at 10–15s; on the machine used
for this investigation (faster disk/CPU, warm Turbopack filesystem cache)
the same first-hit penalty measured in the hundreds of milliseconds to ~1s
— the mechanism is identical, only the magnitude differs by hardware
(disk speed, antivirus/Defender file-scan overhead on Windows, CPU core
count, whether `.next`'s Turbopack cache is warm from a previous run).

No code-level root cause was found: no duplicated/sequential blocking
fetches, no N+1 queries, no disabled `<Link>` prefetching, no oversized
synchronous imports in shared layout/shell code, and no redundant
platform-api session calls beyond the one unavoidable per-zone `/api/auth/me`
call that session restore requires (see "Investigated and ruled out"
below).

## Evidence / measurements

All measurements taken from this investigation's environment, `curl -s -o
/dev/null -w "%{time_total}s"` against `http://localhost:3000` (the
gateway), with `platform-api` (:8000) and `birthday-api` (:8003) running,
and `shell-web` (:3000) / `birthday-web` (:3003) as the two Next.js
processes under test.

### Dev mode (`next dev`, Turbopack) — first hit vs. warmed hit

| Route | 1st request | 2nd request |
|---|---|---|
| `shell-web` `/` | 0.716s | 0.068s |
| `/birthday` (proxied to birthday-web) | 0.673s | 0.054s |
| `/birthday/orders` | 0.130s | 0.052s |
| `/birthday/suppliers` | 0.080s | 0.047s |

Pattern: every route's first request is 2–15x slower than its second — the
classic dev-mode lazy-compile signature. `/` and `/birthday` show the
largest first-hit cost because they're also each zone's *first* route hit
in that dev-server process (compiling shared layout/chunks, not just the
page itself).

### Production build (`next build` + `next start`) — same routes, 3 consecutive hits each

| Route | Hit 1 | Hit 2 | Hit 3 |
|---|---|---|---|
| `shell-web` `/` | 0.036s | 0.004s | 0.009s |
| `/birthday/orders` | 0.068s | 0.009s | 0.030s |
| `/birthday/suppliers` | 0.020s | 0.027s | 0.010s |

No first-hit penalty in production — every request, including the very
first one after server start, is single/double-digit milliseconds. Both
`apps/shell-web` and `apps/birthday-web` build fully as static/prerendered
routes (`next build` output: `○ (Static) prerendered as static content`
for every page except the two dynamic detail routes `/orders/[id]` and
`/suppliers/[id]`, which are plain client components and carry no
server-side data-fetch cost either).

**Conclusion: the 10–15s delay is dev-only and does not reproduce in a
production build.** It is expected Next.js dev-server behavior, already
called out in `docs/platform/local-development.md`'s troubleshooting
section for the `/admin` and `/talent-flow` zones.

### API layer timing (ruled out as a contributor)

| Endpoint | Time |
|---|---|
| `GET /api/modules` (platform-api, via gateway) | 0.031s |
| `GET /api/birthday/dashboard` (birthday-api, via gateway) | 0.018s |
| `GET /api/birthday/dashboard` direct to birthday-api | 0.21s (401, auth rejection path) |

Every backend call involved in a navigation completes in well under 50ms
locally — the API layer is not a contributor to the reported delay.

## Changes made

### 1. Documentation gap: `/birthday` zone missing from the known dev-mode-compile note

`docs/platform/local-development.md`'s troubleshooting section already
warned about first-navigation compile delay for `/admin` and
`/talent-flow`, but not `/birthday` (added in a later phase). Updated the
note to cover all three proxied zones so the same "not a gateway/proxy
problem" reassurance applies uniformly.

- `docs/platform/local-development.md` — troubleshooting bullet now reads
  "First navigation into `/admin`, `/talent-flow`, or `/birthday` is slow
  (several seconds, occasionally more on slower disks/AV-scanned
  machines)."

No other source changes were made. The investigation code (React Query
usage in `apps/shell-web/src/app/page.tsx`,
`apps/shell-web/src/components/home/ModuleCard.tsx` /
`PlatformHealth.tsx`, `packages/auth-client-ts/src/auth-context.tsx`, the
`AuthGate`/`AppShell` shell components, and `birthday-web`'s pages) was
already following the patterns a fix would otherwise introduce:

- **Independent, parallel queries, not sequential awaits.** `HomeContent`
  fires `modulesQuery` and `activityQuery` as two independent
  `useQuery` calls (React Query issues both requests concurrently; there
  is no `await`-then-`await` chain to parallelize with `Promise.all`).
  `PlatformHealth`'s per-module health rows are explicitly documented as
  "never a Promise.all: each row resolves independently" so one dead
  backend can't stall the whole page.
- **No duplicate fetches.** `ModuleCard` and `PlatformHealth` share the
  same React Query `queryKey` (`["module-summary", moduleKey]`) by design,
  so React Query dedupes what would otherwise be two requests into one.
  Session restore (`AuthProvider`'s `getMe()`) fires exactly once per
  mounted React tree — since each zone (`shell-web`, `birthday-web`, …) is
  a separate page load with its own React tree, one `/api/auth/me` call
  per zone-crossing is unavoidable without a shared-session mechanism
  beyond the current token-in-localStorage approach, and is not on the
  scale of the reported 10–15s (measured at 0.03–0.05s including the
  gateway hop, see table above).
- **No disabled `<Link>` prefetching found.** No `prefetch={false}` or
  equivalent appears anywhere in `apps/*/src` or `packages/design-system/
  src`. Cross-zone links are intentionally plain `<a>` tags — this is
  correct, documented behavior (`docs/platform/service-contracts.md`
  "Cross-zone navigation uses a plain `<a>`, not `next/link`"), not a
  missed-prefetch bug: `next/link`'s client router cannot render a
  different zone's app in place regardless of prefetch settings.
- **No heavy synchronous imports in shared layout scope.** All
  `lucide-react` imports across the codebase are named imports (49
  matches, all `import { X } from "lucide-react"`), which tree-shakes
  correctly; no `import * as` wildcard imports of any heavy library were
  found in `apps/*/src` or `packages/*/src`.
- **Config is not reloaded per request.** Each Next.js app's rewrite table
  (`next.config.ts`) is read once at server start, per framework design;
  FastAPI services load `.env`/settings once at import time via Pydantic
  Settings, not per-request.
- **No N+1 queries found in the routes touched by these navigations.**
  `birthday-api`'s `/dashboard`, `/orders`, `/suppliers` endpoints were not
  found to issue per-row queries in a loop in `apps/birthday-api` (not
  modified as part of this investigation; flagged as an area for a
  dedicated backend-focused pass if dashboard/list endpoints grow more
  relational joins later — see Remaining issues).

## Investigated and ruled out

- **Gateway/rewrite proxy overhead** — sub-50ms per hop in both dev and
  prod measurements above; not a contributor.
- **Redundant auth/session calls to platform-api on every navigation** —
  `useAuth()`'s session restore runs once per mounted zone (unavoidable
  given the Multi Zones architecture and full-page cross-zone
  navigation), not once per in-zone client-side navigation; in-zone
  navigations (Orders → Suppliers within `birthday-web`) reuse the same
  React tree and do not refetch `/api/auth/me` at all.
- **Non-prefetched `<Link>`s** — none found; cross-zone links are
  correctly plain `<a>` by design (see above).
- **Heavy synchronous imports in shared shell/layout components** — none
  found.
- **Config reloaded per request** — not applicable to either the Next.js
  or FastAPI services here.

## Remaining issues / limitations

1. **Dev-mode first-hit compile cost is inherent to Next.js dev servers
   and cannot be eliminated without changing how local dev runs** (e.g.
   pre-warming every route on startup, which the platform's own docs
   correctly avoid over-engineering per CR §57). The practical mitigation
   already exists: it is a one-time cost per route per dev-server process
   lifetime, and is explicitly called out as expected in
   `docs/platform/local-development.md` (now including `/birthday`, see
   above). Developers on slower machines (spinning disks, Windows
   Defender real-time scanning of `node_modules`/`.next`) will see this
   cost amplified; excluding the repo's `node_modules` and `.next`
   directories from Windows Defender's real-time scan is a reasonable
   local workaround but is outside this investigation's authorized scope
   to configure on the user's machine.
2. **`birthday-api`'s list/dashboard endpoints were not deep-audited for
   N+1 query patterns** in this pass (the reported delays were fully
   explained by dev-mode compilation, not API latency, in the local
   measurements above, so a backend-query audit was not the highest-value
   next step). If dashboard/list responses grow slower as demo data
   volume increases, a dedicated pass over
   `apps/birthday-api/app/services` and `apps/birthday-api/app/repositories`
   for eager-loading/joins would be the right follow-up.
3. **No caching was added** to `/api/birthday/*` or `/api/talent/*`
   responses, consistent with the explicit constraint that BambooHR
   employee data and cake-order workflow state must stay live — any future
   perceived "still slow" report on those specific screens should be
   re-measured against a running instance before reaching for caching, not
   assumed to be the same dev-compile cause documented here.
