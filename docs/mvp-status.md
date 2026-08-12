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
6. DijiBirthday as the second module, proving the module framework end to
   end (registry → roles → permissions → Admin Center → UI).
