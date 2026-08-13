# DijiOne Failure Isolation (Phase 2.5)

What happens when one DijiOne service is slow, unreachable, or crashed —
and why, service by service. Verified live (not just by unit test) per
CR §47 — see "Live smoke test results" at the bottom.

## The target

```text
talent-api down
      ↓
DijiOne Shell     remains available
Admin Center      remains available
Birthday          remains available
Spark             remains available
```

and symmetrically for any other single service. One dead backend degrades
the one card/page that depends on it — never the whole platform.

## Module status vs runtime status (CR §18)

These are two different axes and DijiOne Home shows both:

- **Product status** (`ApplicationModule.status`): `ACTIVE` or
  `COMING_SOON`. Set by the module registry, changes rarely.
- **Runtime status**: whether the owning service answered its
  `/api/{module}/summary` call just now. Computed per page load, shown as
  a small "● Healthy" / "● Temporarily unavailable" badge on the module
  card (`apps/shell-web/src/components/home/ModuleCard.tsx`).

`DijiBirthday`/`DijiSpark` are `COMING_SOON` — inert teaser cards with no
functional access to gate — so they don't show a runtime badge regardless
of whether `birthday-api`/`spark-api` are actually up.

## DijiOne Home (`shell-web`)

Each module card runs its **own** React Query against its own service's
`/api/*/summary`, with a 4-second `AbortSignal.timeout` and `retry: 0` —
never one `Promise.all` for the whole card grid (CR §39). One card's query
failing renders that card's badge as unavailable; every other card,
including Recent Activity and the rest of the page, is unaffected because
it never awaited the failed query in the first place.

## Admin Center (`admin-web` / `admin-api`)

`admin-api` has two dependencies with two different failure postures:

- **`platform-api`** — not survivable. `admin-api` owns no data of its
  own; every admin screen needs it. A `platform-api` outage surfaces as a
  `503` from `admin-api` (`platform_gateway.call_platform_admin` catches
  `httpx.HTTPError` and raises `HTTPException(503, ...)` rather than
  hanging or crashing unhandled).
- **`talent-api`** — degrades gracefully. Client display names fall back
  to their raw ids, and the dashboard's "Talent Requests Pending Review"
  shows `0` instead of the real count (`talent_gateway.py`'s
  `client_names_map`/`pending_talent_requests` catch `httpx.HTTPError` and
  return an empty map / `0`, logging a warning). User/role/permission
  management — Platform Core's own data — is completely unaffected: **an
  administrator can still manage users while DijiTalentFlow is down**
  (CR §38).

## DijiTalentFlow (`talent-web` / `talent-api`)

`talent-api`'s only outbound dependency is `platform-api`, for audit
events and notifications, and those calls are deliberately best-effort:
`AuditService.log(...)` / `NotificationService.notify_user(...)` /
`.notify_module_role(...)` call `PlatformClient`, which catches
`httpx.HTTPError`, logs a warning, and returns — the talent request,
application, interview, message, or document action the caller was
actually performing still succeeds and still returns `2xx`. A `platform-api`
outage means audit trail/notification gaps during the outage, not failed
talent operations. Verified by
`apps/talent-api/tests/test_talent_request_workflow.py::test_talent_request_creation_survives_platform_core_outage`,
which deliberately points at an unroutable address and asserts the create
still returns `201`.

## Auth: signed claims, not a live dependency

`talent-api`, `birthday-api`, `spark-api` authorize every request from the
JWT's signed claims (`packages/auth-client-py`) — decoded locally, no
database join, no network call to `platform-api` on the request path. This
is the single biggest failure-coupling removal in this phase: pre-split,
every authenticated request needed the one shared database to be up;
post-split, only *logging in* (or refreshing a token) needs `platform-api`
— an already-authenticated session keeps working against `talent-api`
even if `platform-api` is briefly down.

**The accepted trade-off**: permission changes (a module-role edit in the
Admin Center, deactivating a user) take effect the next time the affected
user's token is issued — at login, or whenever a future refresh flow runs
— not instantly. `jwt_expires_minutes` (currently 12 hours in dev) is the
staleness window. This is a deliberate choice per CR §21 ("don't
overengineer, but document the strategy"), not an oversight:

- No revocation list / blocklist is implemented this phase.
- Emergency account disabling (`is_active=false`) still blocks new
  logins immediately — `dev-login` checks it — but an already-issued
  token for that user remains valid for up to its remaining TTL against
  `talent-api`/`birthday-api`/`spark-api` (it does **not** remain valid
  against `platform-api` itself, since `get_current_user` there re-checks
  `User.is_active` from the database on every request).
- A future phase could shorten the TTL, add a lightweight revocation
  check, or move to short-lived tokens with silent refresh — noted as
  follow-up, not built now.

## Live smoke test results

Verified against the real running stack (`npm run dev:all`, all eight
services, seeded demo data), not a mock:

1. Signed in as an ABC Company client persona → DijiOne Home loaded with
   DijiTalentFlow showing "● Healthy", DijiBirthday/DijiSpark showing
   "Coming soon" — all backed by live `/api/talent/summary` /
   `/api/{birthday,spark}/summary` calls.
2. Opened DijiTalentFlow (proxied through to `talent-web`) → Client
   Workspace dashboard rendered real seeded data (2 active requests, 3
   candidates in process, correct per-request progress percentages).
3. Switched persona to `super-admin` → Admin Center dashboard, Users list,
   a user detail page (module access + Effective Access, with **real
   client names**, not raw ids), and the Client Access screen all
   rendered correctly — proving `admin-api`'s pass-through to
   `platform-api` and enrichment from `talent-api` both work live.
4. **Killed `talent-api`'s process.** Refreshed DijiOne Home: page loaded
   normally, DijiTalentFlow's card switched to "● Temporarily unavailable",
   DijiBirthday/DijiSpark cards unaffected. Reloaded Admin Center: Users
   list and Dashboard still fully functional, "Talent Requests Pending
   Review" showed `0` instead of erroring. No 5xx propagated to the
   browser as an unhandled page error; the only failed network calls were
   the expected `/api/talent/summary` requests, handled by the query's
   `isError` state.
5. **Restarted `talent-api`.** Refreshed DijiOne Home: DijiTalentFlow's
   card returned to "● Healthy" with no further action needed.

Zero unexpected browser console errors were observed at any step (one
`next/image` optimizer edge case with `basePath`-proxied local images was
found and fixed — see the `unoptimized` prop on the brand logo in
`packages/design-system/src/shell/Sidebar.tsx` — and one cross-zone
navigation bug, `next/link` silently no-op'ing across a zone boundary,
found and fixed — see `docs/platform/service-contracts.md` "Cross-zone
navigation").
