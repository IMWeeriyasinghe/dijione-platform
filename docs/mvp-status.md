# DijiOne MVP Status

Last updated: end of the Phase 2 autonomous run (see `PLAN.md`). Phase 1
status is preserved below; see "Phase 2 — Authorization & Admin Center"
for what changed.

## Definition of MVP Done — CLAUDE.md §84 checklist (Phase 1)

1. ✅ Repository starts from documented local commands (`docs/setup.md`)
2. ✅ DijiOne Home works
3. ✅ Module registry works
4. ✅ DijiTalentFlow opens inside DijiOne
5. ✅ Client Workspace is functional
6. ✅ TA Workspace is functional
7. ✅ Client tenant isolation works (automated tests, all four vectors)
8. ✅ New talent request workflow works
9. ✅ Customer Success review state exists
10. ✅ Candidate pool works
11. ✅ Candidate can participate in multiple applications
12. ✅ Application stages can be managed
13. ✅ Interviews work
14. ✅ Messaging MVP works
15. ✅ Documents MVP works (metadata; no real file storage yet)
16. ✅ Realistic demo data exists
17. ✅ Audit events are recorded
18. ✅ Notifications exist
19. ✅ Lever adapter architecture exists
20. ✅ HubSpot adapter architecture exists
21. ✅ Mock provider tests pass
22. ✅ Webhook endpoints exist (idempotent)
23. ✅ Entra SSO architecture is documented and code seam exists
24. ✅ Frontend production build passes
25. ✅ Backend tests pass
26. ✅ Migrations work
27. ✅ Design system matches Dijital Team direction (derived palette + real logo)
28. ✅ Documentation reflects the implementation
29. ✅ No secrets are committed

## Quality gates

| Gate | Result |
|---|---|
| `pytest` (apps/api) | 18 passed |
| `ruff check .` (apps/api) | clean |
| Alembic `upgrade head` | clean, single migration |
| `npm run lint` (apps/web) | clean |
| `npm run build` (apps/web) | clean, all routes compile |
| Tenant isolation tests | 6 tests, all four §14 vectors covered |
| Webhook idempotency tests | duplicate delivery produces one `IntegrationEvent` |
| Manual browser smoke test | Playwright-driven, 12 screenshots, 0 console errors — see below |

### Smoke test path (verified in a real headless browser)

Persona switcher → sign in as ABC Company client → DijiOne Home (module
card, greeting, recent activity) → DijiTalentFlow Client Dashboard (real
metrics, request cards matching the CLAUDE.md §32 example exactly, e.g.
62% progress at "Interviews") → My Requests → a request detail page
(vertical stage timeline, tabs) → Candidates tab (client-safe view of Ron
Axel) → switch persona to Madushanka (TA Member) → the *same* request
detail page instantly re-renders with staff controls (Update Stage,
CS/TA status badges, client name shown) → Operations Dashboard → All
Requests → Candidate Pool (Ron Axel correctly shows 2 applications) →
Client Portfolios → Applications (full editable grid) → Interview Manager.

Two real issues were found and fixed during this pass:

1. **CORS default was too narrow.** Next.js falls back to :3001 when :3000
   is occupied by an unrelated local process; the API's CORS allowlist only
   had :3000. Fixed by widening the local-dev default in
   `apps/api/app/core/config.py` (see `docs/setup.md`).
2. **Interview notification body was a raw ISO timestamp.** Fixed to a
   human-readable format in `InterviewService`.

## What was NOT built (by design, not by oversight)

- Live Microsoft Entra ID, Lever, or HubSpot connectivity — no credentials
  supplied, mocks used throughout (CLAUDE.md §58, Phase D not started).
- Real file storage for Documents (Azure Blob/SharePoint) — metadata model
  is ready for it.
- Full Copilot/Cowork integration — architecture documented only.
- A dedicated Customer Success workspace UI distinct from the TA
  Workspace — the `CUSTOMER_SUCCESS` role and review action exist and are
  fully functional inside the TA Workspace shell.

## Estimated completion

Approximately 55-60% of the full DijiOne vision, matching the target for
"First Delivery" in CLAUDE.md §83 — a working platform shell, a fully
functional first module end-to-end, and integration-ready architecture,
without live external connectivity.

## Phase 2 — Authorization & Admin Center

Delivered on top of the Phase 1 baseline above, without rewriting any
working DijiTalentFlow functionality (all 18 pre-Phase-2 tests still pass
unmodified):

1. ✅ Centralized authorization engine (`AuthorizationService`) resolving
   platform + module permissions and client/portfolio scope from database
   state only — see `docs/platform/authorization.md`.
2. ✅ Role / Permission / RolePermission catalog, seeded from a single
   source of truth (`app/core/permissions.py`) used by both the Alembic
   migration and `scripts/seed.py`.
3. ✅ Client/portfolio scope (`UserModuleClientScope`) — staff can now be
   restricted to a subset of clients instead of only "one client" or "all
   clients"; demonstrated by the `ta-portfolio` seed persona (ABC + XYZ
   only, Nova excluded) and covered by
   `tests/test_authorization_phase2.py`.
4. ✅ `SUPER_ADMIN` platform role added alongside `PLATFORM_ADMIN` /
   `PLATFORM_USER`, with lockout protection (last active SUPER_ADMIN can't
   be deactivated/demoted) and admin-role-change restricted to
   `platform.admin.manage_admins` holders.
5. ✅ DijiOne Admin Center — backend (`/api/admin/*`, 15 endpoints) and
   frontend (`/admin/*`, 8 pages: Dashboard, Users, User Detail,
   Applications, Roles, Permissions, Client Access, Audit) — see
   `docs/platform/admin-center.md`.
6. ✅ Module assignments gained an `enabled` flag — disabling a user's
   module access removes it from their DijiOne Home immediately.
7. ✅ `User` gained `entra_object_id`, `identity_provider`,
   `last_login_at` — Phase 2 identity fields, populated on every
   `dev-login`.
8. ✅ Microsoft Entra ID integration seam extended (`/api/auth/entra/*`,
   `app/api/routes/auth_entra.py`) — concrete OIDC code seams that fail
   fast with a typed 501 until real tenant credentials are configured.
   Still not activated; Dev Identity Mode remains the only working
   authentication path.
9. ✅ Every admin mutation is audit-logged via the existing `AuditLog`
   table (no new audit store introduced).
10. ✅ New Alembic migration (`2e7f7d7dc3fa`) applies cleanly to the
    pre-Phase-2 database with a full backfill; verified against both a
    migrated existing `dijione.db` and a fresh `--reset` reseed.

### Phase 2 quality gates

| Gate | Result |
|---|---|
| `pytest` (apps/api) | 35 passed (18 Phase 1 + 17 new Phase 2) |
| `ruff check .` (apps/api) | clean |
| Alembic `upgrade head` | clean, applies to existing dev DB and fresh DB identically |
| `npm run lint` (apps/web) | clean |
| `npm run build` (apps/web) | clean — 8 new `/admin/*` routes compile alongside the 14 existing routes |
| Browser smoke test | Admin Center navigated end-to-end as SUPER_ADMIN; non-admin persona correctly denied with an empty state, not a broken page — see `docs/platform/admin-center.md` |

### DijiBirthday / DijiSpark (CR §4.2 / §4.3)

Registered in the module registry as `COMING_SOON`, rendered as disabled,
non-clickable "Coming Soon" cards on DijiOne Home (`ModuleCard.tsx`
already implemented this correctly in Phase 1). The Admin Center's
Applications screen surfaces them the same way. No functional workflows
were added for either module, per the CR's explicit non-goal.

**Bug found and fixed during Phase 2 browser verification**: both cards'
`required_roles` seed value (`"ANY"`) was a non-empty string, which
`GET /api/modules` treats as "the caller needs an actual module
assignment" — since no persona ever held a `birthday`/`spark` role, this
meant *nobody*, in either phase, ever actually saw the two Coming Soon
cards, contradicting CR §58 Scenario 6. Fixed by seeding
`required_roles=""` for COMING_SOON modules (empty = visible to any
authenticated user, matching the documented intent in
`docs/platform/module-framework.md`); DijiTalentFlow's `required_roles`
is unchanged since it is a real access boundary. Verified in a real
browser (both an ordinary client persona and a no-module-access
SUPER_ADMIN persona now see the two cards) and covered by
`tests/test_module_registry.py`.

## Phase 2.5 — Application-Level Service Separation

Turned the Phase 1/2 modular monolith into eight independently runnable
services (three Next.js frontend apps behind a gateway, five FastAPI
backend services each owning their own data), without rewriting
DijiTalentFlow's business logic or Phase 2's authorization semantics. Full
detail: `docs/platform/service-architecture.md`,
`docs/platform/service-contracts.md`, `docs/platform/failure-isolation.md`,
`docs/platform/local-development.md`.

1. ✅ **Platform Core** (`platform-api`, :8000) — owns identity,
   authorization, module registry, audit log, notifications. Issues JWTs
   carrying signed authorization claims (module roles, permissions, client
   scope) so business services no longer need a database join or a
   synchronous call to authorize a request.
2. ✅ **Admin** (`admin-api`, :8001 / `admin-web`, :3001) — rebuilt as a
   genuinely zero-database service: every `/api/admin/*` request forwards
   to `platform-api` with the caller's own bearer token (never a service-
   asserted identity) and is enriched with `talent-api` data, best-effort.
   Public contract and every screen unchanged from Phase 2.
3. ✅ **DijiTalentFlow** (`talent-api`, :8002 / `talent-web`, :3002) — owns
   its own database (`clients`, `talent_requests`, `candidates`,
   `applications`, `interviews`, `messages`, `documents`,
   `external_mappings`, `integration_events`); no foreign key crosses the
   service boundary. Authorizes purely from JWT claims. Audit/notification
   writes to Platform Core are best-effort (a `platform-api` outage doesn't
   fail a talent action — verified by a dedicated resilience test).
4. ✅ **DijiBirthday** / **DijiSpark** skeletons (`birthday-api` :8003,
   `spark-api` :8004) — health/metadata/summary endpoints and the same
   claims-based auth seam as `talent-api`, no business logic, no database.
   Proves DijiOne can host a new independently bounded application before
   any real workflow exists (CR §9/§10/§51).
5. ✅ Shared packages, not copy-paste: `packages/design-system` (UI
   primitives + shell chrome), `packages/auth-client-ts` (frontend
   session/auth logic), `packages/auth-client-py` (JWT claims verification
   + Platform Core HTTP client), `packages/contracts` (shared TS types).
6. ✅ Gateway routing via Next.js rewrites (`shell-web`'s
   `next.config.ts`) — a browser only ever talks to `localhost:3000`;
   `admin-web`/`talent-web` use Next.js's "Multi Zones" pattern
   (`basePath`) so each remains independently runnable/buildable on its
   own port.
7. ✅ DijiOne Home fetches each service's summary independently (own React
   Query, 4s timeout, `retry: 0`) — never one `Promise.all` — so one dead
   backend degrades one card, never the page (CR §39).
8. ✅ Regression: all pre-existing test coverage re-homed to the owning
   service and green (platform-api 24, admin-api 9, talent-api 27,
   birthday-api 4, spark-api 4, packages/auth-client-py 6 — 74 backend
   tests total), plus new service-isolation and contract tests. All three
   frontend apps build and lint clean.
9. ✅ Live smoke test (CR §47) against the real running stack with seeded
   demo data, including killing `talent-api`'s process mid-session and
   confirming Home/Admin stayed fully functional, then restarting it and
   confirming recovery — see `docs/platform/failure-isolation.md` "Live
   smoke test results" for the full walkthrough and the two real bugs
   found and fixed along the way (a `next/image` + `basePath` proxying
   edge case, and `next/link` silently no-op'ing across a zone boundary).

### What was NOT built (by design, not by oversight)

- Kubernetes, a message broker, a service mesh, distributed tracing, or
  multiple production database servers — explicitly out of scope for this
  phase (CR §57).
- Production Azure infrastructure (Front Door/APIM, Application Insights,
  Key Vault) — documented in `docs/platform/service-contracts.md`
  "Production direction", not provisioned.
- Live Microsoft Entra ID / Lever / HubSpot connectivity — unchanged from
  Phase 1/2, still mock providers only.
- Real DijiBirthday/DijiSpark business functionality — skeletons only, per
  CR §9/§10/§51's explicit non-goal for this phase.
- A permission-change revocation/refresh mechanism for claims-based auth —
  the staleness window (token TTL) is the accepted, documented trade-off
  for this phase (`docs/platform/failure-isolation.md` "Auth: signed
  claims, not a live dependency").

## Phase 2.6 — Enterprise Access Management + Intelligent Home

Delivered on top of the Phase 2.5 service-separated baseline, additive only
— no existing table, endpoint contract, or UI screen was replaced. Full
detail: `docs/platform/access-groups.md`, `docs/platform/effective-access.md`,
`docs/platform/authorization.md` ("Access Groups (Phase 2.6)"),
`docs/platform/admin-center.md` ("Groups screens" / "Applications detail").

1. ✅ **Access Groups** (`platform-api`) — four new additive tables
   (`AccessGroup`, `UserGroupMembership`, `GroupModuleRole`,
   `GroupModuleClientScope`) alongside the untouched
   `UserModuleRole`/`UserModuleClientScope` tables; one new Alembic
   migration.
2. ✅ **Single resolution engine, extended, not duplicated** —
   `AuthorizationService` gained `groups_for_user`, `effective_module_roles`,
   `effective_client_scope`, `effective_permissions`, implementing additive-
   ALLOW resolution (union of direct + active-group grants; ALL_CLIENTS
   overrides any concrete-client-list contributor). Both
   `AdminService.effective_access` (Admin Center) and
   `claims_service.build_claims` (JWT issuance) consume these same combined
   methods.
3. ✅ **Explainability** — `EffectiveModuleAccessOut` gained a
   `sources: list[AccessSourceOut]` field (`DIRECT` vs `GROUP` + group name)
   so the Admin Center's Effective Access tab can show *why* a user has a
   given access, not just *that* they have it.
4. ✅ **SYSTEM group protection** — groups with `group_type="SYSTEM"` are
   rejected from deactivation by `AdminService` (`SystemGroupProtectedError`),
   independent of any frontend check.
5. ✅ **Admin Center** — new Groups screens (list + detail, user-centric
   member/module-assignment editing), new Applications detail screen
   (app-centric: assigned users + assigned groups for one module), User
   Detail refactored into six tabs (Overview / Applications / Groups /
   Client Access / Effective Access / Audit History), Users list gained
   search + client-side filters.
6. ✅ **DijiOne Home redesign** (`shell-web`) — reordered to Header → My
   Apps → Needs Your Attention (new, role-aware, only real data,
   `AttentionPanel.tsx`) → Recent Activity (trimmed to 5) + Platform Health
   (new, rolled up from existing per-module runtime-status fetches) + Ask
   DijiOne (shrunk). Module cards show operational summary fields plus the
   user's resolved role per app; COMING_SOON modules are visually
   de-emphasized. `ModuleCard`/`AttentionPanel`/`PlatformHealth` each keep
   the existing per-service isolated-fetch pattern — no new `Promise.all`
   coupling introduced (CR §39 still holds).
7. ✅ Backend tests: 40 new `platform-api` tests (inheritance rules —
   direct-only/group-only/direct+group union, ALL_CLIENTS override, inactive
   group and disabled-assignment contribute nothing, tenant isolation
   preserved through group paths, SYSTEM group protection, 403s, audit
   coverage) + 12 new `admin-api` pass-through tests, all passing alongside
   the full pre-2.6 suite.
8. ✅ Frontend builds clean: `admin-web` (new `/groups`, `/groups/[id]`,
   `/applications/[key]` routes; refactored `/users/[id]`) and `shell-web`
   (redesigned Home).

### Phase 2.6 final polish (UX + embedded Guide)

9. ✅ **Group Detail Members UX** — the disjointed search-box +
   unfiltered-dropdown + Add button was replaced with one searchable
   `MemberSelector` combobox; the member list now shows Name/Email/Status/
   Action columns with a clean empty state. Same `addGroupMember`/
   `removeGroupMember` APIs, no backend change.
10. ✅ **Admin header alignment** — `TopNav` (shared across admin-web,
    shell-web, talent-web) reworked into a strict left/center/right flex
    layout so notifications and the user avatar sit consistently at the far
    right on every Admin Center route.
11. ✅ **Guide & Access Model** (`/admin/guide`) — new native in-app
    documentation page with a left local Table of Contents (sticky desktop /
    collapsible mobile), an inline SVG access-hierarchy diagram (Entra → User
    → Direct/Group → Role → Permissions → Client Scope → Effective Access →
    Business Application, plus user/application/group-centric views), and a
    full admin manual (Overview through Security Notes) written from the
    platform's real seeded roles/permissions/modules.
12. ✅ **Selective Guide export + module scoping** — `GuideExportDialog`
    lets an admin pick individual sections and/or filter by module
    (Platform / DijiTalentFlow / DijiBirthday / DijiSpark, the latter two
    flagged Coming Soon); Download renders only the selection into a
    branded, chrome-free `print:block` surface and calls `window.print()`
    (Save as PDF) — no new PDF-library dependency.
13. ✅ **Share Guide with Access Group (seam only)** — resolves a chosen
    group's active members via the existing `getAdminGroup(id)` call and
    reports the count; since no email provider (SMTP/SendGrid/etc.) is
    configured anywhere in this codebase, the dialog explicitly states
    delivery is not configured and the "Send Email" action stays disabled —
    no fake "sent" confirmation is ever shown. Download remains fully
    functional as the manual-distribution path.
14. ✅ **Permissions page + contextual help** — explanatory copy above the
    permissions list plus "Learn more in Guide & Access Model"; contextual
    "Learn about…" links added on Groups, Client Access, and a user's
    Effective Access tab.

### Known gaps (documented, not oversights)

- Users list has no group-count column/filter — `AdminUserOut` doesn't
  carry a `groups` field; would need a backend change, left as a documented
  gap rather than an N+1 client-side fetch on the list screen (see
  `docs/platform/admin-center.md` "Users list improvements").
- User Detail's Groups tab derives membership by cross-referencing every
  group's detail client-side rather than a dedicated
  `GET /api/admin/users/{id}/groups` endpoint — fine at current scale, noted
  as a future improvement.
- `birthday-api`/`spark-api`'s `/summary` endpoints return only
  `service`/`status`/`product_status` (no operational counts), so their
  DijiOne Home cards show no operational stats line — expected, they remain
  skeletons per CR §9/§10/§51.
- No claims-refresh/revocation mechanism for group-derived access — a group
  membership or module-role change takes effect at the affected user's next
  login/token refresh, exactly the same documented staleness trade-off
  direct assignment changes already have (`docs/platform/failure-isolation.md`
  "Auth: signed claims, not a live dependency"; see also
  `docs/platform/effective-access.md` "Claims staleness").

## Next autonomous phase (when resumed)

1. Request read-only Lever + HubSpot credentials (Phase D discovery).
2. Update `LEVER_STAGE_MAP` against real pipeline data.
3. Implement `EntraAuthProvider.decode_token` (JWKS validation) and the
   Next.js `/api/auth/callback` route once a real Entra app registration
   and tenant/client credentials are available — the `/api/auth/entra/*`
   seam is ready to receive it.
4. Real document storage (Azure Blob Storage).
5. Role/permission creation-and-editing UI in the Admin Center (currently
   read-only/system-protected).
6. Real DijiBirthday business functionality on top of the Phase 2.5
   skeleton — BambooHR birthday source, cake ordering, duplicate
   prevention — proving the full module framework end to end (registry →
   roles → permissions → Admin Center → UI → its own service).
7. Consider a lightweight claims-refresh or revocation mechanism if the
   Phase 2.5 token-TTL staleness window proves too coarse in practice.
