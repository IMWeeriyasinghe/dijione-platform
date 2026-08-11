# DijiOne MVP Status

Last updated: end of the first autonomous run (see `PLAN.md`).

## Definition of MVP Done — CLAUDE.md §84 checklist

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

## Next autonomous phase (when resumed)

1. Request read-only Lever + HubSpot credentials (Phase D discovery).
2. Update `LEVER_STAGE_MAP` against real pipeline data.
3. Build the Entra ID `EntraAuthProvider` once tenant/client credentials
   are available.
4. Real document storage (Azure Blob Storage).
5. DijiBirthday as the second module, proving the module framework.
