# DijiBirthday — Phase 1 Definition of Done

Tracks the Phase 1 completion plan
(`C:\Users\Dell\.claude\plans\dijione-dijitalentflow-rippling-cascade.md`).
Legend: ✅ done · 🔄 automated + deploying · ⏳ pending a human validation step.

## Build (phases 1.0–1.8) — ✅

| Phase | Item | State |
|---|---|---|
| 1.0 | `MISSING_EMPLOYEE_NUMBER` typed exception (no silent fallback) + recovery on PATCH | ✅ |
| 1.0 | VERIFIED refused for an order with no delivery destination at all | ✅ |
| 1.0 | `docs/birthday/{requirements,end-to-end-workflow}.md` rewritten to the shipped model; "14 states" → 13 | ✅ |
| 1.1 | Working-day-aware delivery-date rule (`delivery_date_service`) + `DELIVERY_DATE_ADJUSTED` event | ✅ |
| 1.2 | Attention/SLA + detection-health engine (`attention_service`) — digest notifications, `birthday-attention-job` | ✅ |
| 1.2 | Dashboard cards: on-hold, overdue delivery, open issues + unmatched emails, detection health | ✅ |
| 1.3 | Outbound email automatic backoff retry + retry-exhaustion notification + `EMAIL_RETRY_EXHAUSTED` | ✅ |
| 1.3 | Duplicate-send guard; post-release change/cancel → supplier email nudge | ✅ |
| 1.4 | Communication subsystem: one extended `SupplierCommunication` store, bidirectional Portal messaging, one audience-filtered Unified Timeline | ✅ |
| 1.4 | Consolidated the dual change-request / cannot-fulfil paths (one typed `OrderIssue`; only `CANNOT_FULFIL` moves status) | ✅ |
| 1.5 | Inbound supplier email — **polling only** (§H.0): `birthday-comms-job`, `inbound_email_service`, quarantine table, Unmatched-email queue, dev inject endpoint | ✅ |
| 1.5 | Matched inbound email → **one `SupplierCommunication` + notification, NO auto `OrderIssue`** (free text is not an exception) | ✅ |
| 1.6 | `SupplierUser` onboarding-state (`invited_at`/`linked_at`/`last_login_at` + derived state) + setup-readiness panel | ✅ |
| 1.6 | `docs/birthday/supplier-onboarding-runbook.md` | ✅ |
| 1.7 | Frontend: dashboard cards, Unmatched-email page, Order Detail Unified Timeline + reply (both apps), Cake Orders saved views, supplier list default-sort + overdue flag, Supplier Detail readiness/chip | ✅ |
| 1.8 | Component tests for the new surfaces | ✅ |
| — | Migrations `d1e3f5a7b9c2`, `e2f4a6b8c0d2`, `f3a5b7c9d1e4` — additive/nullable, up/down/up verified | ✅ |
| — | Tests: `birthday-api` 243 · `birthday-web` 6 · `birthday-supplier-web` 7 · both production builds green | ✅ |

### Deferred with rationale
- **Browser-level Playwright E2E** — the repo has no Playwright harness and running one needs a live 6-service stack (a new tooling/CI surface). The four critical journeys are covered end-to-end at the API layer (`test_dry_run_e2e.py`, `test_communication_subsystem.py`, `test_inbound_email.py`, `test_attention_service.py`) + the new component tests. Follow-up item.

## Deploy + real DEV validation (phase 1.9)

| Step | State | Note |
|---|---|---|
| Bicep: `birthdayIntegrationsMode=live` param + `birthday-attention-job` + `birthday-comms-job` | ✅ | `az bicep build` clean |
| Build + deploy `birthday-api` / `birthday-web` / `birthday-supplier-web` to hosted DEV | ✅ | commit `97fb35a`; digests `birthday-api@sha256:608571cc…`, `birthday-web@sha256:1a3ea949…`, `birthday-supplier-web@sha256:9cf14a34…`. (Built via `git archive` → clean 11 MB context — the raw-worktree `az acr build` upload hangs on Windows.) |
| `birthday-api` `INTEGRATIONS_MODE=live` (consumes live People via people-api) | ✅ | `EMAIL_SENDING_MODE` stays `mock`; `SUPPLIER_AUTH_MODE=entra` |
| `migrate-birthday-api` (applies `d1e3f5a7b9c2`, `e2f4a6b8c0d2`, `f3a5b7c9d1e4`) | ✅ | execution `Succeeded` |
| `/health/deep` smoke | ✅ | `status: healthy`, `database: ok`, `migration up_to_date: true` (`f3a5b7c9d1e4`), `integrations_mode: live`, `email_sending_mode: mock`, `people_source: ok` (when people-api warm) |
| `birthday-attention-job` + `birthday-comms-job` execute cleanly | ✅ | both `Succeeded` on the deployed image |
| Real detection scan on live data | ✅ | `birthday-scan-job` `Succeeded` → **27 orders created** (`birthday_dev` was 0), 8 exceptions (expected: skeleton "Test Supplier" has no location/catalogue → NO_SUPPLIER/NO_DEFAULT_CAKE) |
| Web surfaces serving | ✅ | `shell-web/birthday` 200, `birthday-supplier-web` login + `login-url` 200 |
| Realistic DEV supplier (location + default cake + working days + real `SupplierUser`) | ⏳ | internal-admin action via `/birthday/suppliers` — this is what clears the 8 detection exceptions |
| **Interactive human Entra B2B sign-in** + the §N checklist (auth → match → oid → session → portal → isolation → logout → persona-404) | ⏳ | requires a person at a browser |
| Run detection on live data; inspect every order (eligibility, exceptions, defaulting, address snapshot, weekend shift) | ⏳ | `POST /admin/run-detection` |
| Drive 3 orders end-to-end by hand; read the Unified Timeline | ⏳ | |
| Communication round-trip — all four §G flows incl. the inbound inject + quarantine | ⏳ | dev inject endpoint |
| Failure injection (people-api cold → deferred; email fail → retry → exhaust; deactivate user/supplier; cross-supplier 404) | ⏳ | |
| Log defects; triage P0 fixed / rest P1–P2 | ⏳ | |

## UAT entry (blocked until)
- All P0 merged (done) + the 1.9 ⏳ validation steps executed and PASS
- Browser E2E (deferred item) resolved or explicitly accepted
- Real Graph outbound + inbound email enabled and proven **in UAT** (Graph app reg + `Mail.Send` + `Mail.Read` + admin consent + shared mailbox + KV secrets `birthday-graph-*`)
- Supplier onboarding runbook executed for a real supplier in UAT
- Monitoring/alerting wired to the platform's real alert sink

## Production entry (blocked until)
See the plan §T — real email proven, alerting live, backup/rollback/support runbook signed off, `ApplicationModule` row confirmed `ACTIVE` in the target env.
