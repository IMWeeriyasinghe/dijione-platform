# DijiTalentFlow V1 traceability register

Evidence level: **Local** means developed and passing automated tests on a
workstation, with SQLite and mocked integrations. Nothing here is CI verified,
hosted verified or business accepted unless a row says so.

| WP | Requirement | Frontend | Backend | Tests | Status | Remaining |
|---|---|---|---|---|---|---|
| 01 | Coverage register | n/a | n/a | n/a | This document | Keep current |
| 02 | TA dashboard, truthful metrics | `TaDashboardView` | `dashboard_service` | `test_client_portfolio_metrics`, `test_v1_workflow_hardening`, `talent.spec` | Local | Hosted check |
| 03 | Client and portfolio scope | `clients/*` | `deps.py`, repositories | `test_portfolio_scope_mutations`, `test_tenant_isolation`, `talent.spec` | Local | Restricted test users in UAT |
| 04 | Requests from verified postings | `requests/*` | `verified_posting_promotion_reconciler` | `test_verified_posting_promotion`, `talent.spec` | Local; pipeline verified in UAT at Phase 1 | Request stage is staff-updated |
| 05 | Candidates, applications, sharing | `candidates/*`, `ApplicationsView` | `application_service` | `test_candidate_ownership`, `test_external_candidate_review`, `talent.spec` | Local | None known |
| 06 | Interviews and confidentiality | `InterviewList` | `interview_repo` | `test_client_access_security`, `talent.spec`, `portal.spec` | Local | None known |
| 07 | Customer Success review | `ReviewRequestModal` | `review_request`, decided requests locked | `test_talent_request_workflow`, `talent.spec` | Local | None known |
| 08 | External portal | `talentflow-portal-web` | `talent_external` | `test_external_access`, `portal.spec` | Local | Hosted run |
| 09 | Read-only Lever | Sync panel | `live_client`, sync services | `test_lever_client_safety`, `test_live_client_resilience` | Local | Live duration measurement |
| 10 | Completeness | Partial status shown | Per-posting reads, heartbeat, `PARTIAL` | `test_opportunity_completeness`, `test_sync_run_lifecycle` | Local | Compare totals with Lever in UAT |
| 11 | Mapping and withdrawal | `PostingsView` | `client_access_service` | `test_client_access_security`, `test_posting_mapping_unmap` | Local | None known |
| 12 | P0-3/4/5/6, P1-4 | Callback route | `deps.py`, DTOs | `test_client_access_security`, `route.test.ts`, `portal.spec` | Local | Hosted check |
| 13 | Access links | `AccessLinksView` | `magic_link_service` | `test_external_access`, `test_external_grant_admin`, `portal.spec` | Local | Portal URL per environment; rate-limit source (runbook) |
| 14 | Notifications and audit | Platform inbox | Best-effort `notification_service`, `audit_service` | `test_notification_delivery` | Local | Alert on undelivered log line |
| 15 | HubSpot, BambooHR, Spark Hire | None | None | Boundary test | Not Required for V1 | None |
| 16 | Screen behaviour | Errors surfaced, including failed sharing | n/a | Vitest, both Playwright suites, `a11y.spec` in both apps | Local | Design-system accessibility items below |
| 17 | Validation and integrity | n/a | Stage, TA status, candidate checks | `test_v1_workflow_hardening` | Local; no migration needed | PostgreSQL run in CI |
| 18 | Automated and E2E | Playwright in `web.yml` | pytest | Release report | Local | First CI run |
| 19 | Release procedure | n/a | n/a | n/a | `v1-release-runbook.md` | Execute on approval |
| 20 | Readiness report | n/a | n/a | n/a | Delivered per round | Update after CI |

## The six scope items

| Item | Classification | Evidence |
|---|---|---|
| New Talent Request | Explicitly out of V1: retired 2026-09-01 | The route always returns 403 and its docstring records the retirement. No role holds `talent.requests.create`. `CLAUDE.md` §34 is older and was not updated |
| Customer Success intake queue | Explicitly out of V1: follows from the retirement | Verified requests are auto-approved by design, so a queue would be empty or fictional. The review action remains for any request awaiting review |
| Portal feedback | Explicitly out of V1 | `talent_external.py` defines the portal as a fixed read-only set with no create or update route. `CLAUDE.md` assigns "managing feedback" to Dijital Team |
| Real document storage | Explicitly deferred | `requirements.md`, "Explicitly deferred". The screen now says only details are recorded |
| Module Admin | Genuine product decision | Built on local branch `local/talent-module-admin` (4 commits, not pushed, 94 behind the Talent line). No document makes it V1. Including it needs a merge approval |
| Automatic stage progression from Lever | Genuine product decision | Application stage and status already follow Lever. Request stage is deliberately TalentFlow-owned (`reconcile_posting_facts`). Rolling candidates up to a request stage needs a business rule |

## Proposals awaiting approval

**Module Admin.** Not needed for daily V1 administration. Mapping, access links
and sync status are already available in Postings, Access Links and the sync
panel. The branch mainly regroups these screens under `/admin` and adds
`talent.admin.*` capabilities. If wanted after V1: rebase its four commits onto
the release line in a new branch, renumber its platform migration
`j0k1l2m3n4o5` against the current head, re-apply this release's portfolio and
withdrawal rules to `talent_admin.py`, and test the moved Access Links route.
Merge through a separate PR.

**Automatic request stage (recommended rule, not implemented).** The request
stage would be the furthest canonical stage reached by any active application,
and would only move forward. TA keeps a manual override, which automation never
reverses. Rejected or withdrawn applications do not count. `CLIENT_REVIEW`,
`ONBOARDING` and `DEPLOYED` stay TA-set unless the business confirms a matching
Lever stage. Until approved, TA manages the stage manually.

## Accessibility

An axe WCAG 2.1 A/AA audit runs on staff and portal screens in `a11y.spec`.
TalentFlow has its own dialog with focus containment and restoration, labelled
controls, announced errors, and darker text tokens in its own stylesheets. The
portal's footer text is overridden locally.

Text-only shades are darker in TalentFlow's stylesheets; the brand primary
`--dt-orange` and the red and amber brand colours are unchanged.

The shared `UserMenu` button gained `aria-label` and `aria-expanded`, with no
visual change. It still labels sign-out "Switch persona" under Entra. The shared
`Modal` still lacks dialog semantics for other modules.

Browser suites are not repeat-safe for two tests: customer review and grant
revocation each consume one seed record, so `--repeat-each` fails them after
the first pass. Their assertions are unchanged.

## Known limits

- A Lever tag change takes effect at the next reconcile; staff unmapping is
  immediate. Notifications already delivered cannot be recalled.
- The 200 most-recent cap remains for untagged postings, a business exclusion.
  Client-tagged postings are read in full, subject to the 180 s budget; a run
  that hits the budget records `PARTIAL`.
- Notifications are one best-effort attempt with no retry.
- On re-tag, the previous client loses messages and documents; staff keep them
  on the retired request, per the instruction that the old client must lose
  access immediately.
- The shared user menu labels sign-out "Switch persona", including under Entra.
