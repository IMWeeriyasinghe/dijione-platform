# DIJI Birthday — Technical Handover

> Audience: the next coding agent, working from the MacBook clone at
> `/Volumes/SD_APFS/Diji Projects/DijiOne/dijione-platform`.
> Scope: DIJI Birthday only (`birthday-api`, `birthday-web`, `birthday-supplier-web`,
> the Birthday jobs, `packages/mail-client-py` as Birthday uses it). Platform facts
> appear only where they change what Birthday does.
>
> Supersedes as the *current* reference: `docs/platform/DIJIBIRTHDAY-CURRENT-STATE-HANDOVER.md`
> (a 2026-09-09 snapshot; still useful for per-page UI detail, but its environment,
> email and deployment sections are out of date).

---

## 0. Status block

| Field | Value |
|---|---|
| **CURRENT STATUS** | Phase 1 feature-complete in code. **Deployed to PROD** (internal UI, supplier portal, API, 3 jobs). PROD outbound mail is **CONFIGURED AND EXCHANGE-AUTHORIZED — LIVE-SEND VALIDATION PENDING A GENUINE ORDER**. Newest Birthday work (supplier invitations, portal deep link in order email) is **DEV-only** and lives on a branch that is **not** in the current integration line. |
| **LAST VERIFIED** | 2026-11-13 (repo, GitHub, and live Azure read-only inspection in this session) |
| **CONTINUATION BRANCH** | `docs/birthday-handover` (this doc) = `origin/feat/onsite-dashboard-v1` @ `ab2f5f8` + docs. For new *development*, see §19 — start a reconciliation branch from `origin/release/onsite-v1`. |
| **LAST SAFE COMMIT (newest Birthday code)** | `ab2f5f8` — `chore(birthday,docs): fix time-dependent tests and lint; add macOS setup (#78)` |
| **PROD BIRTHDAY CODE** | Images built 2026-09-17 14:20 UTC; consistent with Birthday source at `92c8482` (no git-SHA tag on the image — inferred from build time; `cc09e86`, the next commit, touches only UAT params). |
| **NEXT PRIORITY** | P0-1: reconcile the two diverged lineages so Birthday's latest code **and** PROD IaC params live on the integration branch (`release/onsite-v1`). See §18. |

---

## 1. Executive status

**What it is.** DIJI Birthday (DijiBirthday) detects upcoming employee birthdays from
the People directory, creates one `BirthdayOrder` per employee per year, drives
address verification and release, emails the order to a cake supplier, and gives the
supplier an external portal to accept / progress / raise issues on their orders.

**Maturity.** Phase 1 complete in code; 356 backend tests + 123 frontend tests pass
locally at `ab2f5f8`. Running in DEV, UAT and PROD. PROD has **0 orders**
(read-only query, prior session) so no real business traffic has flowed yet.

**Complete:** detection + eligibility, order state machine (incl. dedicated CANCELLED
reopen), address verification, auto/confirm release, supplier admin (locations,
catalogue, users, readiness), supplier portal with Entra B2B sign-in, read-only
impersonation, attention/SLA sweep, outbound email via Graph + managed identity,
Email Safety allowlist (non-prod), inbound-email triage UI, supplier invitations
(DEV only), portal deep link in supplier email (DEV only).

**Deployed:** see §12/§13. PROD = 2026-09-17 build. UAT = same API/web/portal digests as PROD
(non-prod registry). DEV `birthday-api` + `birthday-supplier-web` run the invitation-workflow
build (2026-09-28); DEV `birthday-web` still runs the 2026-09-17 build.

**Still requires work / partially broken** (details §8, §17):
1. Lineage divergence — newest Birthday code + PROD Entra/integration params are missing
   from `release/onsite-v1`, where every recent PR (#80–#100) merged. `main` has neither.
2. PROD `birthday-web` has no `APP_ENV` → Email Safety nav item is shown to PROD admins and its
   page 404s.
3. PROD mail settings exist only as ad-hoc runtime env vars, not Bicep.
4. `EMAIL_SENDING_MODE=mock` in PROD: inbound supplier-email polling is mocked, and the
   DEV-only `internal/dev/inbound-email` injector is enabled in PROD (token-guarded).
5. Live-send validation in PROD not yet done (no genuine order exists).

**Do first:** §18 P0-1 (reconciliation branch), then P0-2 (`APP_ENV` on PROD `birthday-web`, needs approval).

---

## 2. Repository / Git state (proved 2026-11-13)

| Item | Value |
|---|---|
| Working branch at handover start | `feat/onsite-dashboard-v1`, tracking `origin/feat/onsite-dashboard-v1`, HEAD `ab2f5f8`, in sync with remote |
| Uncommitted work found | `deploy/README.md` — a Birthday-relevant note ("`az containerapp update --image` does not update the `migrate-<service>` job"), verified against a real DEV incident. **Committed on `docs/birthday-handover`** as its own commit. |
| `origin/main` | `e21fdb2` (2026-09-03). **Stale for Birthday.** Missing Email Safety, Graph mail, `PLATFORM_JWT_SECRET` rename, all env Bicep params. Do not base Birthday work on `main`. |
| `origin/release/onsite-v1` | `6e20849` (2026-11-13). The live **integration branch**: PRs #80–#100 merged here (AtWork, TalentFlow, On-site, replica floors). Contains Birthday up to `92c8482` (Graph mail, Email Safety, transport_outcome). |
| `origin/feat/onsite-dashboard-v1` | `ab2f5f8`. The **only** branch with the newest Birthday commits. Its On-site commits were re-applied to `release/onsite-v1` under new hashes, so the two lines diverged at `cc09e86`. |

### Commits that exist ONLY on `feat/onsite-dashboard-v1` (patch-equivalence checked with `git log --cherry-pick`)

| Commit | Date | Subject | Birthday? | Cherry-pick onto `release/onsite-v1` (dry run) |
|---|---|---|---|---|
| `8ac99f8` | 09-18 | fix(infra): make existing role assignments reproducible across environments | infra | CONFLICT `main.bicep`, `main.uat.bicepparam` |
| `9d1478b` | 09-18 | config(prod): wire confirmed PROD Entra registrations; fix promote.sh ACR import | **PROD Entra IDs incl. supplier portal** | CONFLICT `main.prod.bicepparam` |
| `d4efb92` | 09-18 | config(prod): enable canonical client-directory bootstrap for PROD | platform/talent | CONFLICT `main.prod.bicepparam` |
| `d6512fb` | 09-29 | fix(birthday-web): invalidate supplier readiness after location/user changes | yes | clean |
| `8dca96b` | 09-29 | feat(deploy): enable live BambooHR/Lever integrations for UAT and PROD | **sets `birthdayIntegrationsMode='live'`** | CONFLICT both bicepparams |
| `70bcd6a` | 09-29 | feat(birthday): redesign supplier order email with a Supplier Portal deep link | yes | clean |
| `18de64c` | 09-29 | feat(birthday): Supplier Portal invitation workflow (auto + manual send) | yes (adds migration `ad84ec92abcb`) | clean |
| `eb3dfdf` | 10-22 | build(onsite): deployment, CI and module-boundary enforcement | no (On-site; differs from release's `6983df5`) | not attempted |
| `ab2f5f8` | 11-09 | chore(birthday,docs): time-dependent tests, lint, macOS setup (#78) | yes | CONFLICT `docs/platform/local-development.md` only |

Dry run result: with `d6512fb 70bcd6a 18de64c` applied on `release/onsite-v1`, birthday-api
tests ran 195 passed, then 1 failure — `test_detection_defaults_delivery_date_to_birthday_occurrence`,
the time-dependent test that `ab2f5f8` (#78) fixes. So #78 has to come along too.
The throwaway worktree was removed; nothing was pushed.

**Why this matters:** PROD's current runtime has `INTEGRATIONS_MODE=live` and the PROD supplier
Entra client ID, but `release/onsite-v1:deploy/bicep/main.prod.bicepparam` has **no**
`birthdayIntegrationsMode`, `peopleIntegrationsMode`, `entraClientId`, `supplierEntraClientId`
or `supplierPublicBaseUrl`. A full `main.bicep` PROD run from `release/onsite-v1` would fail
(intentional fail-closed on missing Entra IDs) or, if those were patched, revert Birthday to
mock People data. Targeted release templates (`onsite-release.bicep`, `atwork-release.bicep`)
don't touch Birthday, which is why it hasn't bitten yet.

### Stale / do-not-continue branches (for Birthday)

- `main` — too old (see above).
- `pr-43`, `local/*`, `test/frontend-vitest-4-apps` — local-only experiments.
- Dependabot PRs #15–#18 (birthday-api deps) and #77 target `main`; leave them. Rebase or re-raise
  after the lineage is reconciled.
- `.worktrees/*` on the Windows machine are TalentFlow/platform worktrees, not Birthday.

---

## 3. Architecture

```
 Internal staff ──► https://dijione[-dev|-uat].dijitalteam.com  (shell-web, external)
                      │  /birthday/*      ─► birthday-web  (internal ingress)
                      │  /api/birthday/*  ─► birthday-api  (internal ingress)
                      │  /api/auth/*      ─► platform-api  (issues DijiOne JWT)
 Suppliers ─────────► https://supplierportal[-dev|-uat].dijitalteam.com (birthday-supplier-web, external)
                      │  /api/birthday/portal/*        ─► birthday-api
                      │  /api/birthday/supplier/auth/* ─► birthday-api
                      │  /api/birthday/internal/dev/*  ─► birthday-api (DEV personas; 404 unless SUPPLIER_AUTH_MODE=dev)
                      │  /login, /api/auth/callback, /impersonate = app's own route handlers
 Jobs (curl) ───────► http://birthday-api/api/birthday/internal/{run-daily-scan|run-attention|run-comms}
 birthday-api ──────► http://people-api   (employee directory; never BambooHR, never People DB)
              ──────► http://platform-api (platform calls)
              ──────► Microsoft Graph sendMail as appassistant@dijitalteam.com (system-assigned MI)
              ──────► own PostgreSQL DB (secretRef database-url-birthday)
```

### Frontend — `apps/birthday-web` (internal)
- Next.js, `basePath: "/birthday"`, internal ingress only. Reached only through `shell-web`
  (`/birthday/:path*` rewrite; shell env `BIRTHDAY_WEB_URL=http://birthday-web`).
- Pages: `/` dashboard, `/upcoming`, `/orders`, `/orders/[id]`, `/suppliers`, `/suppliers/[id]`,
  `/inbound-emails`, `/admin/email-safety` (non-prod only). Own route `/birthday/api/meta`
  returns `{release_date, is_production}` from `RELEASE_DATE` / `APP_ENV`.
- Calls go through `src/lib/api.ts` → `@dijione/auth-client` `request()` → `/api/birthday/*`
  (rewritten with `basePath:false` to `BIRTHDAY_API_URL`).
- Auth: DijiOne session (Entra in all hosted envs) carrying `module_roles.birthday`.
  No Birthday role → "No DijiBirthday access" empty state.

### Supplier portal — `apps/birthday-supplier-web` (external)
- Separate Next.js app, no basePath, **external** ingress with custom domain.
- Pages: `/` dashboard, `/orders`, `/orders/[id]`; route handlers `/login`, `/api/auth/callback`,
  `/impersonate`.
- Talks only to `/api/birthday/portal/*` and `/api/birthday/supplier/auth/*` (plus the dev
  persona prefix). Must never call internal `/orders` or `/suppliers` endpoints — enforced by
  convention in `src/lib/api.ts`. Keep it that way; never share components or tokens with
  `birthday-web`.
- Session: supplier JWT (minted by birthday-api) in `sessionStorage` key
  `dijibirthday-supplier-token`; 8 h TTL; impersonation tokens 30 min, read-only.

### Backend — `apps/birthday-api` (internal)
- FastAPI. Routers in `app/api/routes/`: `birthday` (metadata/summary/whoami), `dashboard`,
  `orders`, `suppliers`, `employees` (+ `people` router), `config`, `admin`, `inbound_email`,
  `portal`, `supplier_auth_entra`, `dev_auth`, `internal`, `health`.
- Services (`app/services/`): `detection_service`, `eligibility_service`, `order_service`,
  `order_status_service` (state machine + `reopen_cancelled_order`), `order_email_service`
  (send / resend / retry / ad-hoc), `supplier_email_template`, `supplier_invitation_service`
  (DEV branch only), `inbound_email_service`, `communication_service`, `address_verification_service`,
  `supplier_auth`, `test_email_recipient_service`.
- Integrations (`app/integrations/`): `people_source/` (HTTP adapter → people-api; mock adapter),
  `inbound_mail/` (mock / Graph client-credentials), `factory.py` (mail client + policy wiring).
- Owns its own DB; no other service reads it.
- Startup calls `assert_trust_anchors_safe` — refuses to boot outside development with default
  `PLATFORM_JWT_SECRET` / `INTERNAL_SERVICE_SECRET`.

### Jobs (all Container Apps Jobs, image = birthday-api, PROD on `crdijioneprod`)

| Job | Trigger (UTC) | What it runs | Business logic in job? | Deployed |
|---|---|---|---|---|
| `birthday-scan-job` | Schedule `0 19 * * *` | `curl -fsS -X POST` `/internal/run-daily-scan` with `X-Internal-Token` | No — calls birthday-api | DEV/UAT/PROD; PROD runs Succeeded nightly through 2026-11-12 |
| `birthday-attention-job` | Schedule `30 20 * * *` | `/internal/run-attention` (SLA/attention sweep) | No | DEV/UAT/PROD; PROD Succeeded 2026-11-12 |
| `birthday-comms-job` | Schedule `*/10 * * * *` | `/internal/run-comms` = outbound retry sweep + inbound poll | No | DEV/UAT/PROD; PROD Succeeded 2026-11-13 08:10 |
| `migrate-birthday-api` | Manual | `alembic upgrade head` (env `APP_ENV`, `DATABASE_URL`) | Migrations only | DEV/UAT/PROD; **no PROD execution history visible** (retention) — PROD DB revision not re-verified this session |

Jobs carry only the image digest for the migrate job; the curl jobs' image is irrelevant to
behaviour (they run the API's code). **The migrate job's image must be bumped with the API** —
see `deploy/README.md` "Fourth follow-up".

---

## 4. Domain rules / invariants (checked against code at `ab2f5f8`)

| Rule | Status in code | Where |
|---|---|---|
| Never read BambooHR directly | ✅ Holds. Only reference is the DTO field `bamboohr_id` mapped from people-api's response. No BambooHR credential in birthday-api env. | `app/integrations/people_source/http_adapter.py` |
| Employee data only via `people-api` | ✅ `PEOPLE_API_URL=http://people-api`, `INTEGRATIONS_MODE=live` in all envs | `people_source/`, `factory.py` |
| No People DB access | ✅ No People DB URL/secret anywhere in birthday-api | — |
| Order snapshots employee data | ✅ `employee_id`, `employee_number`, `employee_name`, `employee_email`, `birthday_date`, `office_location` stored on `birthday_orders` | `app/models/birthday_order.py` |
| Existing orders operable during People outage | ✅ Order routes read the snapshot; only detection/upcoming/freshness call people-api | — |
| People outage defers scanning | ✅ `ScanRunStatus.DEFERRED_SOURCE_UNAVAILABLE`, endpoint still returns 200 so the job doesn't flap; consecutive-defer threshold surfaced in health | `internal.py`, `constants.py`, `health.py` |
| Supplier identity is server-side | ✅ `get_supplier_scope` re-loads `SupplierUser` per request; `supplier_id` taken from the DB row, never URL/body; cross-supplier order ids 404 | `app/api/deps.py` |
| No auto-create of SupplierUser on Entra sign-in | ✅ `resolve_supplier_user` matches by `entra_object_id`, else by email (then links oid); never creates; non-ACTIVE → generic 403 | `app/services/supplier_auth.py` |
| COMPLETED never reopens | ✅ `ALLOWED_TRANSITIONS[COMPLETED] = set()` | `order_status_service.py` |
| CANCELLED reopen only via dedicated command | ✅ `CANCELLED: set()` in the transition table; `reopen_cancelled_order()` is the sole exit, behind `birthday.orders.reopen` | `order_status_service.py:285` |
| Email is an independent seam | ✅ All outbound via `get_email_client()`; transport and policy are separate; null transport by default | `app/integrations/factory.py` |
| PROD email ignores DEV/UAT allowlist | ✅ `MAIL_POLICY=production` → `ProductionPolicy`; Email Safety admin routes 404 in PROD via `require_non_production` | `factory.py`, `deps.py:78` |

**Discrepancies / caveats:**
- `SIMULATED` counts as *business-accepted*: with null transport the communication row is
  recorded `status=SENT`, `transport_outcome=SIMULATED`. UAT has no `MAIL_*` vars, so **UAT never
  sends real email** but its UI will show "sent". That's intended, but don't read UAT "sent" as
  proof of delivery.
- The DEV-only inbound-email injector is gated on `EMAIL_SENDING_MODE == "mock"`, not on
  environment — and PROD has `EMAIL_SENDING_MODE=mock`. See §17.

---

## 5. Database / data model

Own PostgreSQL database per environment (`DATABASE_URL` from secret `database-url-birthday`).

### Tables (`app/models/`)
`birthday_orders`, `suppliers`, `supplier_users`, `supplier_locations`, `supplier_catalogue_items`,
`supplier_communications`, `order_events`, `order_issues`, `special_requirements`, `scan_runs`,
`detection_config`, `order_sequence`, `inbound_emails`, `birthday_test_email_recipients`.

### Key relationships
- `birthday_orders.supplier_id → suppliers.id` (nullable); `catalogue_item_id → supplier_catalogue_items.id`
- `supplier_users.supplier_id → suppliers.id` (CASCADE); `email` unique; `entra_object_id` unique
- `supplier_communications.order_id → birthday_orders.id` (CASCADE); `supplier_id → suppliers.id`;
  `issue_id → order_issues.id` (SET NULL)

### Enums (`app/core/constants.py`)
- `OrderStatus`: PENDING_VERIFICATION, REQUIRES_REVIEW, REQUIRES_ATTENTION, ON_HOLD, SENT_TO_SUPPLIER,
  CHANGE_REQUESTED, CONFIRMED, PREPARING, OUT_FOR_DELIVERY, DELIVERED, COMPLETED, UNABLE_TO_FULFIL, CANCELLED
- `ExceptionReason`: MISSING_EMAIL, MISSING_EMPLOYEE_NUMBER, NO_SUPPLIER, NO_DEFAULT_CAKE, SHORT_NOTICE_LEAD_TIME,
  ADDRESS_MANUALLY_CORRECTED, DELIVERY_DATE_CHANGED, QUANTITY_CHANGED, CAKE_OVERRIDDEN, SUPPLIER_OVERRIDDEN,
  SEND_FAILED, DELIVERY_FAILED, SUPPLIER_CANNOT_FULFIL
- `AddressVerificationStatus`: NOT_CHECKED, VERIFICATION_REQUESTED, VERIFIED, NEEDS_UPDATE, NOT_APPLICABLE
- `LeadTimeClass`: NORMAL, SHORT_NOTICE, URGENT · `ScanRunStatus`: COMPLETED, DEFERRED_SOURCE_UNAVAILABLE
- `CommunicationDirection`: OUTBOUND, INBOUND · `CommunicationChannel`: EMAIL, PORTAL, SYSTEM, TEAMS
- `CommunicationStatus`: QUEUED, SENT, FAILED, DELIVERED, REPLIED, POSTED
- `OrderIssueType`: CHANGE_REQUEST, CANNOT_FULFIL, DELIVERY_ISSUE, OTHER · `OrderIssueStatus`: OPEN, RESOLVED
- `BirthdayRole`: BIRTHDAY_USER, BIRTHDAY_ADMIN, BIRTHDAY_SUPPLIER
- `SupplierUser.status`: ACTIVE / INACTIVE (string)

### Lifecycle (happy path)
`PENDING_VERIFICATION` →(verify / auto-release)→ `SENT_TO_SUPPLIER` →(supplier accept)→ `CONFIRMED` →
`PREPARING` → `OUT_FOR_DELIVERY` → `DELIVERED` → `COMPLETED`. Flagged orders go via `REQUIRES_REVIEW`
(one-click confirm-release). Send failures → `REQUIRES_ATTENTION` (retry/resend). `ON_HOLD` from any
pre-send state. `UNABLE_TO_FULFIL → REQUIRES_ATTENTION`. Sendable states: PENDING_VERIFICATION,
REQUIRES_REVIEW, REQUIRES_ATTENTION.

### Migrations (`apps/birthday-api/alembic/versions/`) — linear chain
```
dcde696849a5 initial → cb458018416c address_verification_status → a1b2c3d4e5f6 employee_number
→ b2c3d4e5f6a7 delivery/catalogue/entra fields → c3d4e5f6a7b8 supplier_user role
→ f3a91c7b2e04 delivery_address → e7f2a0b1c9d3 approval provenance → f8b3d1a4c206 suppliers.is_default
→ a1c9e3f5b7d2 semi-automation state machine → b2d4f6a8c1e3 scan_run status
→ c4f6a8b0d2e4_drop_mock_orders → d1e3f5a7b9c2 communication subsystem → e2f4a6b8c0d2 inbound_email
→ f3a5b7c9d1e4 supplier_user onboarding → a4c6e8f0b2d5 actor_display_name on order_events
→ 729cb1d84e60 supplier_communications.transport_outcome   (added in f382401)
→ ab10ac1cdce1 birthday_test_email_recipients              (a8b747d)  ← head on release/onsite-v1 = expected PROD/UAT head
→ ad84ec92abcb supplier_users.invite_count/last_invited_by (18de64c)  ← head on feat/onsite-dashboard-v1 / DEV
```
`transport_outcome` migration: `729cb1d84e60` (down_revision `a4c6e8f0b2d5`), `String(16)`, nullable.
PROD DB's actual `alembic_version` was **not** queried this session.

---

## 6. API inventory (`birthday-api`, at `ab2f5f8`)

All under `/api/birthday` unless noted. "perm" = `require_birthday_permission(...)` against the
DijiOne JWT's `module_roles.birthday.permissions`. "sup" = `require_supplier_permission(...)` +
ACTIVE SupplierUser re-check. "internal" = `require_internal_service` (`X-Internal-Token`).
"Verified" = route exists, has a matching frontend caller, and tests pass locally; no endpoint was
called against a hosted environment this session.

### Health / metadata
| Method | Route | Auth | Caller | Notes |
|---|---|---|---|---|
| GET | `/health`, `/health/deep` (no prefix) | none | ACA probes, ops | deep shows `mail_transport`, `mail_policy`, `email_sending_mode`, people-source health |
| GET | `/metadata` | none | platform | module metadata |
| GET | `/summary` | none (DB counts) | shell-web Home card (`ModuleCard.tsx`) | verified caller |
| GET | `/whoami` | JWT | debugging | no UI caller |

### Dashboard / directory
| GET | `/dashboard`, `/upcoming` | perm `dashboard.read` | birthday-web `/` | ✅ |
| GET | `/employees/upcoming-birthdays` | perm `dashboard.read` | `/upcoming` | ✅ (calls people-api) |
| GET | `/people/freshness` | perm `dashboard.read` | `/upcoming` | ✅ |
| POST | `/people/refresh` | perm `config.manage` | `/upcoming` | ✅ |

### Orders (internal)
| GET/POST | `/orders` | `orders.read` / `orders.create` | `/orders` | ✅ filters: search, status_filter (csv), lead_time_class, office_location, supplier_id, address_verification_status, due, has_open_issue, verify, acceptance, sort_by, sort_direction, page, page_size — all dashboard deep-links match |
| GET/PATCH/DELETE | `/orders/{id}` | read / update / delete | OrderDetail | ✅ |
| GET | `/orders/{id}/readiness` | read | OrderDetail | ✅ |
| POST | `/orders/{id}/verify` | `orders.verify` | OrderDetail | ✅ verification == approval; may auto-release |
| POST | `/orders/{id}/confirm-release` | `orders.review` | OrderDetail | ✅ REQUIRES_REVIEW → send |
| POST | `/orders/{id}/hold`, `/release` | `orders.hold_release` | OrderDetail | ✅ |
| POST | `/orders/{id}/cancel` | `orders.cancel` | OrderDetail | ✅ |
| POST | `/orders/{id}/reopen` | `orders.reopen` | OrderDetail | ✅ CANCELLED only |
| PATCH | `/orders/{id}/address-verification`, `/delivery-address` | update | OrderDetail | ✅ |
| POST | `/orders/{id}/special-requirements` | update | OrderDetail | ✅ |
| GET/POST | `/orders/{id}/issues`; PATCH `/issues/{issue_id}/resolve` | read/update | OrderDetail | ✅ |
| GET | `/orders/{id}/timeline` | read | OrderTimeline | ✅ |
| POST | `/orders/{id}/messages` | update | OrderDetail (ad-hoc supplier message — emails supplier) | ✅ |

### Supplier send / resend
| POST | `/orders/{id}/send-to-supplier` | `orders.send_supplier` | OrderDetail | ✅ duplicate-send guard |
| POST | `/orders/{id}/resend` | `orders.send_supplier` | OrderDetail | ✅ explicit resend bypasses guard by design |

### Supplier admin
| GET/POST | `/suppliers`; GET/PATCH `/suppliers/{id}` | `suppliers.read` / `suppliers.manage` | `/suppliers*` | ✅ |
| GET/POST | `/suppliers/{id}/locations` | read / manage | SupplierDetail | ✅ |
| GET/POST/PATCH | `/suppliers/{id}/catalogue[/{item_id}]` | read / manage | SupplierDetail | ✅ |
| GET | `/suppliers/{id}/readiness` | read | SupplierDetail | ✅ |
| GET/POST/PATCH | `/suppliers/{id}/users[/{user_id}]` | read / manage | SupplierDetail | ✅ |
| POST | `/suppliers/{id}/users/{user_id}/impersonate` | manage | SupplierDetail → opens `{SUPPLIER_PUBLIC_BASE_URL}/impersonate` | ✅ 30-min read-only token |
| POST | `/suppliers/{id}/users/{user_id}/invite` | manage | SupplierDetail | ⚠️ **only in DEV `birthday-api` image** — not in UAT/PROD images. See §8 #3 |

### Config / admin / email safety
| GET/PATCH | `/config` | `config.manage` | dashboard admin | ✅ |
| POST | `/admin/run-detection`, `/admin/run-attention`; GET `/admin/scan-runs` | `config.manage` | dashboard admin (run-detection, scan-runs) | ✅ (run-attention has no UI caller) |
| GET/POST/PATCH/DELETE | `/admin/test-email-recipients[/{id}]` | `config.manage` + `require_non_production` (404 in PROD) | `/admin/email-safety` | ✅ DEV/UAT; ❌ **PROD page is reachable and 404s** — §8 #1 |
| GET | `/inbound-emails`; POST `/{id}/link`, `/{id}/dismiss` | `orders.read` / `orders.update` | `/inbound-emails` | ✅ (PROD inbound is mock-polled, so nothing real arrives) |

### Internal / jobs
| POST | `/internal/run-daily-scan`, `/internal/run-attention`, `/internal/run-comms` | internal | the 3 jobs | ✅ PROD runs Succeeded |
| GET | `/internal/scan-runs[/{run_id}]` | internal | ops | — |
| POST | `/internal/dev/inbound-email` | internal + `EMAIL_SENDING_MODE==mock` | manual DEV testing | ⚠️ **enabled in PROD** (mock mode) — §17 |

### Supplier authentication (public, via supplier portal)
| GET | `/supplier/auth/config` | none | login-screen | ✅ |
| GET | `/supplier/auth/login-url` | none (needs Entra configured) | `/login` route handler | ✅ PKCE + signed flow token, `return_to` sanitized |
| POST | `/supplier/auth/token` | flow token + code | `/api/auth/callback` | ✅ resolves ACTIVE SupplierUser or generic 403 |
| GET | `/internal/dev/supplier-users`; POST `/internal/dev/supplier-login` | `require_dev_mode` (SUPPLIER_AUTH_MODE=dev) | local persona picker | ✅ 404 in all hosted envs (all are `entra`) |

### Supplier portal
| GET | `/portal/me`, `/portal/dashboard` | sup `portal.access` | portal `/` | ✅ |
| GET | `/portal/orders` | sup `portal.access` | portal `/orders` | ✅ filters status_filter, due (today/tomorrow/overdue), has_open_issue, completed=today — all dashboard links match |
| GET | `/portal/orders/{id}`, `/timeline`, `/issues` | sup `portal.access` | portal `/orders/[id]` | ✅ |
| POST | `/portal/orders/{id}/accept`, `/issues`, `/messages`; PATCH `/status` | sup `portal.respond` (+ not read_only) | portal `/orders/[id]` | ✅ |

**Role grants** (`apps/platform-api/app/core/permissions.py`): `BIRTHDAY_USER` = dashboard.read, orders.read,
suppliers.read. `BIRTHDAY_ADMIN` = every Birthday permission except portal.*. `BIRTHDAY_SUPPLIER` =
portal.access, portal.respond (minted by birthday-api into supplier tokens, not granted via platform UI).

---

## 7. Frontend route / API link audit

Method: extracted every path from `apps/birthday-web/src/lib/api.ts` and
`apps/birthday-supplier-web/src/lib/api.ts` + route handlers, every `href`/`router.push`, and the
query parameters each page reads; compared against the birthday-api OpenAPI schema generated
from `ab2f5f8`; checked rewrites in both `next.config.ts` files and `shell-web/next.config.ts`;
read live env of all Birthday apps in DEV/UAT/PROD.

**Result at source level: no frontend→API path mismatches.** Every path called by either web app
exists with the matching method, and every dashboard deep-link query param is accepted by the API.
No hard-coded DEV/UAT/PROD hostnames in Birthday frontend source (all upstreams env-driven with
localhost fallbacks). Email links are built from `SUPPLIER_PUBLIC_BASE_URL` (`{base}/orders/{id}`),
which is set correctly per env. The problems are deployment/environment ones:

## Known Broken / Suspected Broken Routes and Links

| # | File / path | Caller / link | Expected target | Symptom | Likely root cause | Severity | Fixed? | Next action |
|---|---|---|---|---|---|---|---|---|
| 1 | `apps/birthday-web/src/app/birthday-shell.tsx` nav + `/admin/email-safety` page; `src/app/api/meta/route.ts` | "Email Safety" nav → `GET /api/birthday/admin/test-email-recipients` | Nav hidden in PROD | **PROD**: nav item shown to BIRTHDAY_ADMINs; page loads, API returns 404 (by design), page shows an error | `is_production = APP_ENV === "prod"`, and PROD `birthday-web` has **no `APP_ENV`** (verified live). Bicep sets `APP_ENV` only for `kind=='api'` | Medium (no safety impact: the backend still refuses; UX/confusion only) | No | P0-2: set `APP_ENV=prod` on PROD birthday-web (approval needed); long-term add `commonWebEnv` in `main.bicep` |
| 2 | `birthday-web` footer (`/birthday/api/meta`) | `RELEASE_DATE` | Release date shown | UAT/PROD footer shows no release date | `RELEASE_DATE` only set ad hoc in DEV | Low | No | Fold into the same Bicep web-env fix |
| 3 | `apps/birthday-web/src/lib/api.ts:267` (`inviteSupplierUser`) | `POST /suppliers/{id}/users/{uid}/invite` | birthday-api invite route | Would 404 if HEAD `birthday-web` were deployed against the UAT/PROD API image; in **DEV** the API has it but the DEV web (older image) has no Invite button | Version skew: invite route added in `18de64c`, only DEV `birthday-api`/`supplier-web` were updated | Medium (deploy-ordering trap) | No | Always deploy birthday-api (+ migrate job) **before or with** birthday-web; P1-1 |
| 4 | `apps/birthday-supplier-web/next.config.ts` rewrite `/api/birthday/internal/dev/:path*` | Public supplier domain → `internal/dev/*` | Only dev persona routes | In PROD, `POST /api/birthday/internal/dev/inbound-email` is reachable from the internet and **enabled** (EMAIL_SENDING_MODE=mock); still requires `X-Internal-Token` | Rewrite prefix broader than the two persona routes; injector gated on mail mode, not environment | Medium (defense-in-depth) | No | P1-3: narrow the rewrite to `supplier-users`/`supplier-login` and gate the injector with `require_non_production` |
| 5 | Supplier order email (PROD image, pre-`70bcd6a`) | No portal link in the email | `{SUPPLIER_PUBLIC_BASE_URL}/orders/{id}` deep link | PROD suppliers get an email without a portal link | `70bcd6a` not deployed beyond DEV | Low–Medium | Fixed in code (DEV only) | Ships with P0-1 + P1-1 |
| 6 | Internal access via `https://dijione.dijitalteam.com/birthday` | DijiOne shell sign-in / callback | Shell session → Birthday | A PROD shell auth issue has been reported by the user; **not investigated here** | Platform (shell-web / platform-api), not Birthday. Related platform work: `28232d0` (callback inline script), PR #86 (Entra account linking) — both on `release/onsite-v1` | Depends on platform | Unknown | Track as an external dependency; Birthday can't be used internally until it's resolved, but don't debug it in birthday-api |

Checked and OK: supplier `/login` → `/supplier/auth/login-url` → Entra → `/api/auth/callback` →
`/supplier/auth/token` (redirect URIs `https://supplierportal[-dev|-uat].dijitalteam.com/api/auth/callback`
match live `SUPPLIER_ENTRA_REDIRECT_URI`); `return_to` sanitized in three places; impersonation URL
uses `SUPPLIER_PUBLIC_BASE_URL`; CORS origins include the supplier ACA fqdn per env; shell Home card
`/api/birthday/summary`.

---

## 8. Email implementation

### Shared library — `packages/mail-client-py`
Shared **source code**, vendored into each service image. It is not a mail service and has no
runtime of its own. It provides `MailClient(transport, policy)`, `MailResult`, `MailOutcome`,
`GraphMailTransport` (DefaultAzureCredential → Graph `sendMail` as one shared mailbox),
`NullMailTransport`, and policies (`DisabledPolicy`, `InternalAllowlistPolicy`, `ProductionPolicy`).
22 tests pass.

### Birthday owns
- Its **own** system-assigned managed identity (the Graph credential) — no client secret for outbound.
- Its own config: `MAIL_TRANSPORT`, `MAIL_POLICY`, `MAIL_SHARED_MAILBOX` (`app/core/config.py`).
- Policy wiring: `app/integrations/factory.py::_build_policy` (not cached — allowlist read live from
  `birthday_test_email_recipients` each send; DB error → fail closed).
- Templates: `app/services/supplier_email_template.py` (DEV branch) / inline in
  `order_email_service.render_supplier_email` (PROD build).
- Audit + idempotency: every attempt writes a `SupplierCommunication` row with `status`,
  `transport_outcome`, `message_id`, `retry_count`, `next_retry_at`, `last_error`; an `OrderEvent`
  records `correlation_id` + outcome. Duplicate-send guard `_has_successful_release` makes
  auto-release / send / confirm-release no-ops after one successful release; resend and the retry
  sweep deliberately skip the guard. Backoff retries by `birthday-comms-job`, `max_attempts=5`.

### Outcomes (`MailOutcome`)
| Outcome | Meaning | `MailResult.sent` | Birthday business-accepted? |
|---|---|---|---|
| NOT_ATTEMPTED | never reached transport | False | no |
| DISABLED | `DisabledPolicy` (default / unknown policy) | False | no → FAILED row |
| BLOCKED | allowlist refused recipient | False | no → FAILED row, distinct `last_error` |
| SIMULATED | null transport | False | **yes** (`_BUSINESS_ACCEPTED_OUTCOMES`) → row `SENT` |
| SUBMITTED | Graph accepted the send | **True (only case)** | yes |
| FAILED | Graph/transport error | False | no → retry |

`MailResult.sent=True` only for `SUBMITTED` — confirmed in `transport.py` and `graph_transport.py:101`.

### Environment behaviour (live 2026-11-13)
| | DEV | UAT | PROD |
|---|---|---|---|
| `MAIL_TRANSPORT` | `graph` | *(unset → null)* | `graph` |
| `MAIL_POLICY` | `internal_allowlist` | *(unset → disabled, but null transport → ProductionPolicy → SIMULATED)* | `production` |
| `MAIL_SHARED_MAILBOX` | `appassistant@dijitalteam.com` | *(unset)* | `appassistant@dijitalteam.com` |
| Real email leaves? | Yes, **only** to active Email Safety recipients | **Never** | Yes, to the assigned supplier |
| Email Safety UI | shown, active | shown (no effect: transport is null) | API 404; nav wrongly shown (§7 #1) |
| `EMAIL_SENDING_MODE` | `mock` | `mock` | `mock` |

`EMAIL_SENDING_MODE` **does not** control outbound mail any more. It only selects the **inbound**
poll client (`mock` → `MockInboundMailClient`) and enables `/internal/dev/inbound-email`. So in PROD:
outbound = real Graph; inbound supplier replies = **not polled** (mock). Real inbound needs
`EMAIL_SENDING_MODE` ≠ mock **plus** `GRAPH_TENANT_ID/CLIENT_ID/CLIENT_SECRET/INBOX_MAILBOX` for the
client-credentials inbound client — none of which are configured. Inbound in PROD is unbuilt config,
not a regression. Background: `docs/platform/email-architecture.md`, `docs/birthday/email-safety.md`.

---

## 9. PROD email status

| Item | Value | Verified this session |
|---|---|---|
| `birthday-api` identity | SystemAssigned (+ a UserAssigned for ACR pull) | ✅ |
| MI principal / object id | `87788d4c-3036-4f2f-ac1d-83eb9a5e7a13` | ✅ (`az containerapp show`) |
| MI app id | `597d63ed-ba5f-47e1-b2f4-b70ec36c282c` (SP display name `birthday-api`, type ManagedIdentity) | ✅ (`az ad sp show`) |
| Exchange service principal | `DIJIBirthday-Prod-API-MI` | prior session only |
| Exchange RBAC role assignment | `DIJIBirthday-Prod-MailSend` (Application Mail.Send) | prior session only |
| Management scope | `DijiApps-AppAssistant-Mailbox-Scope` | prior session only |
| Scope test | `appassistant@dijitalteam.com` InScope=True; a personal mailbox InScope=False | prior session only |
| Runtime | `MAIL_TRANSPORT=graph`, `MAIL_SHARED_MAILBOX=appassistant@dijitalteam.com`, `MAIL_POLICY=production`, `EMAIL_SENDING_MODE=mock` | ✅ live |
| Source of runtime mail vars | `az containerapp update --set-env-vars` (ad hoc). **Not in Bicep on any branch** (`git grep MAIL_TRANSPORT deploy/bicep` → nothing) | ✅ → IaC debt |

Exchange checks need `Connect-ExchangeOnline` (`Get-ManagementRoleAssignment`, `Test-ServicePrincipalAuthorization`);
not re-run here.

## 10. PROD live-send validation

A read-only query in the previous session returned `BirthdayOrder count = 0`. No live supplier email
was sent, and **no fake order was created**.

**Status: CONFIGURED AND EXCHANGE-AUTHORIZED — LIVE-SEND VALIDATION PENDING A GENUINE ORDER.**

Safe validation path once a genuine order exists (needs business approval, not a test order):
1. Genuine order detected by the nightly scan (19:00 UTC).
2. Supplier assigned, with an ACTIVE location + default catalogue item (supplier readiness green).
3. Release via the supported path only (verify → auto-release, or confirm-release / send-to-supplier in the UI).
4. Order timeline: `OrderEvent` detail shows `transport_outcome=SUBMITTED` + correlation id.
5. `supplier_communications` row: `status=SENT`, `transport_outcome=SUBMITTED`, `sent_at` set, `last_error` null.
6. No duplicate: exactly one successful OUTBOUND release row; repeat clicks no-op.
7. Delivery: supplier confirms receipt; Sent Items of `appassistant@dijitalteam.com`; Exchange message trace.
If outcome is `FAILED`, read `last_error`; don't hit resend repeatedly — the comms job retries with backoff.

---

## 11. Deployment environments (live 2026-11-13)

Resource groups `rg-dijione-{dev,uat,prod}`, region southeastasia. DEV/UAT pull from
`crdijionenonprod.azurecr.io`; PROD from `crdijioneprod.azurecr.io`.

| | DEV | UAT | PROD |
|---|---|---|---|
| Internal UI URL | `https://dijione-dev.dijitalteam.com/birthday` | `https://dijione-uat.dijitalteam.com/birthday` | `https://dijione.dijitalteam.com/birthday` |
| Supplier portal URL (external) | `https://supplierportal-dev.dijitalteam.com` | `https://supplierportal-uat.dijitalteam.com` | `https://supplierportal.dijitalteam.com` |
| ACA env domain | `livelypebble-890e141a` | `mangofield-96838df7` | `icybush-52a8142b` |
| `birthday-api` (internal) | `sha256:edbfe6a0…ef43` (2026-09-28, invitation workflow) | `sha256:98656e2e…cd` | `sha256:98656e2e…cd`, minReplicas 1 |
| `birthday-web` (internal) | `sha256:9584a369…a1` | `sha256:9584a369…a1` | `sha256:9584a369…a1` |
| `birthday-supplier-web` (external) | `sha256:c7c9d048…b57` (2026-09-28) | `sha256:ef97b18b…e3` | `sha256:ef97b18b…e3` |
| `migrate-birthday-api` | edbfe6 | 98656e | 98656e |
| scan / attention / comms jobs | 98656e (curl only — fine) | 98656e | 98656e |
| `APP_ENV` (api / web) | development / development | uat / **unset** | prod / **unset** |
| Integrations | live (people-api) | live | live |
| Supplier auth | entra, client `30e36193-f0e4-40d5-875b-db1ef6a3f2b0` | entra, `bdd98d91-1fe9-4b81-b621-96fa14d2e9b5` | entra, `572564e5-acad-495b-92e7-029ecabba8e7` |
| Tenant | `2abce006-6ea2-4675-b39d-33e0a54c46c7` (all) | | |
| Email | graph + internal_allowlist | null (simulated) | graph + production |
| Known issues | web image older than api (no Invite UI); `RELEASE_DATE`/`APP_ENV` ad hoc | web `APP_ENV` unset (harmless: API not prod either) | §7 #1, #4, #5; §8 inbound mock; mail vars ad hoc |

Secrets referenced (names only): `database-url-birthday`, `jwt-{dev,uat,prod}-secret` (as `PLATFORM_JWT_SECRET`),
`internal-service-secret`, `birthday-supplier-entra-secret-{dev,uat,prod}`.

## 12. PROD deployment baseline (verified live 2026-11-13)

| App | Digest | ACR created |
|---|---|---|
| `birthday-api` (+ all 4 Birthday jobs) | `sha256:98656e2eed0cf267dbf126f03ab09ee9d44ac5b7079ac99f6d0b42025cb34ccd` | 2026-09-17 19:48 UTC (imported; non-prod build 14:20 UTC) |
| `birthday-web` | `sha256:9584a36965885ce8553887bc2924ee559e035fb597efa59e9fde4a413c1df1a1` | 2026-09-17 19:49 UTC |
| `birthday-supplier-web` | `sha256:ef97b18b822a09d452fb57c1be4327b58497498f190b0a8b15ce5d7c706a3ae3` | 2026-09-17 19:49 UTC |

All PROD Birthday apps and jobs reference only `crdijioneprod.azurecr.io` (registries and images checked);
`birthday-api` PROD JSON contains no `nonprod`, DEV/UAT env domains or `-dev.`/`-uat.` hostnames.
Promotion is `deploy/promote.sh` (ACR import by digest), never a rebuild.

---

## 13. Authentication

### Internal Birthday
- User signs in to `shell-web` via Microsoft Entra (`authMode=entra`; PROD internal client id
  `98b1f056-68a2-492e-9d37-ae2e5eb0d218`, from `9d1478b`'s bicepparam). platform-api mints an HS256
  DijiOne JWT (`PLATFORM_JWT_SECRET`) with `module_roles.birthday = {role, permissions[]}`.
- birthday-api validates it locally with `auth_client_py` and checks permission keys per route (§6);
  it holds no role table. Admin role: **`BIRTHDAY_ADMIN`**, granted through DijiOne Admin.
- A shell sign-in problem blocks Birthday internal access but is a platform defect, not Birthday.

### Supplier portal
- Entra ID B2B guest, Authorization Code + PKCE, run by birthday-api (`supplier_auth_entra.py`);
  the supplier-web only relays (`/login` stores a 10-min httpOnly flow cookie; `/api/auth/callback`
  posts code + state + flow token to `/supplier/auth/token`).
- birthday-api verifies the id_token, then `resolve_supplier_user`: match `entra_object_id`, else email
  (links oid on first match); must be **ACTIVE**; never auto-creates. Failure → generic 403.
- Mints a supplier JWT (8 h; `supplier` claim with `supplier_user_id`; module role BIRTHDAY_SUPPLIER).
  Every portal request re-loads the SupplierUser and takes `supplier_id` from the row.
- Impersonation: admin mints a 30-min `read_only` token with `impersonated_by`; write routes refuse it.
- Onboarding (inviting the guest into the tenant) is a human step: `docs/birthday/supplier-onboarding-runbook.md`,
  `docs/platform/birthday-supplier-authentication.md`.
- Known callback issues: none found in Birthday code; redirect URIs match live config.

---

## 14. Git / PR history (Birthday-relevant, chronological)

Birthday work was mostly direct commits, not PRs.

| When | Ref | What |
|---|---|---|
| 2026-09-09 | `071ccd6`, `14da6d6`, `16fbd8c`, `4551f4d`, `5a54fff`, `7614dd4`, `94fa997`, `f69cba8`, `34f2bfd`, `caf257d`, `cf9b16d`, `a1f8d0d` | Phase 1.2–1.9: inbound email, attention/SLA, supplier admin/onboarding, frontends, tests, DEV deploy, handover doc |
| 2026-09-14 | `7a49fc3`, `d54ba38`, `75f2fc0`, `b355e7a`, `394527a`, `9ea594d`, `e60f899`, `398002a` | Phase 1.6 hardening, reopen, responsive work, version footer |
| 2026-09-14 | **`f382401`** | Real Microsoft Graph outbound email via shared `mail-client-py` + Managed Identity; adds `transport_outcome` (`729cb1d84e60`) |
| 2026-09-15 | `a8b747d`, `e819196` | Email Safety allowlist (`ab10ac1cdce1`) + docs (send-to vs Exchange RBAC send-as) |
| 2026-09-17 | `92c8482`, `cc09e86` | `PLATFORM_JWT_SECRET` rename; UAT Entra params. **PROD Birthday images built from here** |
| 2026-09-18 | `9d1478b`, `d4efb92`, `8ac99f8` | PROD Entra registrations + promote.sh fix, PROD bootstrap, role-assignment IaC (**only on feat/onsite-dashboard-v1**) |
| 2026-09-29 | `d6512fb`, `8dca96b`, `70bcd6a`, `18de64c` | readiness fix, live integrations for UAT/PROD params, email deep link, invitation workflow (`ad84ec92abcb`). DEV-deployed only |
| 2026-11-08/09 | PR **#78** → `feat/onsite-dashboard-v1` (`7db82d7` squashed as `ab2f5f8`) | time-dependent test fixes, lint, macOS setup docs. CI all green (incl. `lint-test (birthday-api)`, `pg (birthday-api)`, `lint-build (birthday-web|birthday-supplier-web)`) |
| 2026-11-09 → 11-13 | PRs #80–#100 → `release/onsite-v1` | AtWork, TalentFlow, On-site, replica floors. **#97** adds PROD `minReplicas` for `birthday-api` (live: 1). No other Birthday changes |

Open PRs touching Birthday: only Dependabot #15–#18 (birthday-api deps, base `main`) and #77 (npm group,
base `main`). No PR introduced a frontend/API route mismatch. No open PR carries the Birthday commits
from the table in §2.

---

## 15. Test status (run locally on Windows at `ab2f5f8`, 2026-11-13)

| Suite | Result | Class |
|---|---|---|
| `apps/birthday-api` pytest (SQLite) | **356 passed, 1 skipped** (2 m 13 s); only deprecation warnings | — |
| `packages/mail-client-py` pytest | **22 passed** | — |
| `apps/birthday-web` vitest | **96 passed / 17 files** | — |
| `apps/birthday-supplier-web` vitest | **27 passed / 6 files** | — |
| CI on PR #78 (last CI touching Birthday) | all checks pass, incl. Postgres job `pg (birthday-api, birthday_dev)` | — |
| `test_detection_defaults_delivery_date_to_birthday_occurrence` **without #78** | fails (date-dependent) | **KNOWN FLAKE** — fixed by `ab2f5f8`; recurs on any branch lacking #78 (e.g. `release/onsite-v1`) |
| Postgres suite locally | not run this session | NOT INVESTIGATED |
| E2E against hosted envs / Graph live send | none | NOT INVESTIGATED (by design until a genuine order) |

Coverage gaps: no test asserts web `APP_ENV` presence/is_production in deployed config; no test ensures
`internal/dev/*` is unreachable in production.

---

## 16. Known issues / technical debt

| Priority | Area | Issue | Impact | Current state | Recommended action |
|---|---|---|---|---|---|
| P0 | Git / IaC | Lineage divergence: newest Birthday code + PROD Entra/integration bicepparams only on `feat/onsite-dashboard-v1` | Next full PROD deploy from integration branch breaks or regresses Birthday; Birthday fixes can't ship via the normal path | Verified (§2) | Reconciliation branch, P0-1 |
| P0 | Config / UI | PROD `birthday-web` lacks `APP_ENV` → Email Safety visible and broken in PROD | Admin confusion; looks like a broken page | Verified live | P0-2 |
| P1 | IaC drift | PROD `MAIL_*` set by `az containerapp update --set-env-vars`, absent from Bicep everywhere | Full `main.bicep` deploy silently returns PROD mail to null/disabled | Verified | P1-2: add `birthdayMailTransport/Policy/SharedMailbox` params |
| P1 | IaC drift | Web `APP_ENV`, `RELEASE_DATE` ad hoc (DEV) / missing (UAT/PROD) | Same wipe risk; §7 #1–2 | Verified | P1-2 |
| P1 | Security hardening | `/internal/dev/inbound-email` enabled in PROD (`EMAIL_SENDING_MODE=mock`) and publicly routable via supplier-web rewrite (token-guarded) | Anyone with the internal token could inject fake supplier replies in PROD | Verified in code + live env | P1-3 |
| P1 | Release | Invitation workflow, deep-link email, readiness fix not in UAT/PROD | PROD suppliers get no portal link / no invite emails | DEV only | P1-1 |
| P1 | Env drift | DEV web older than DEV api | Invite feature untestable in DEV UI | Verified | Redeploy DEV birthday-web from the reconciled branch |
| P1 | Validation | PROD live send never exercised | Unknown real-world Graph behaviour | 0 orders | §10 when a genuine order exists |
| P2 | Inbound mail | Inbound polling mocked in all envs; no Graph inbound credentials | Supplier email replies aren't ingested anywhere; portal is the only reply channel | By config | Product decision; don't change silently |
| P2 | Ops | PROD `migrate-birthday-api` execution history empty; DB revision not re-verified | Uncertain schema head before next migration | Unverified | Query `alembic_version` read-only before the next PROD migration |
| P2 | Exchange | RBAC scope verified in prior session only | Drift unknown | — | Re-run `Test-ServicePrincipalAuthorization` before live send |
| P2 | Deps | Dependabot #15–#18, #77 target stale `main` | Noise | Open | Re-target after reconciliation |
| P2 | Tests | No guard tests for web `APP_ENV` / dev-route exposure | Regressions slip through | — | Add with P1-2/P1-3 |
| P3 | Branching | `main` is months behind the integration branch | Confusing default branch | — | Owner decision; out of Birthday scope |

---

## 17. Exact next steps

### P0 — Immediate blockers

**P0-1 Reconcile Birthday onto the integration line.**
- Why: Birthday's newest code and PROD's real IaC params aren't on `release/onsite-v1`.
- Areas: `apps/birthday-*`, `deploy/bicep/main.prod.bicepparam`, `main.uat.bicepparam`, `main.bicep`, `deploy/promote.sh`, `docs/platform/local-development.md`.
- Branch: `git switch -c chore/birthday-reconcile-release origin/release/onsite-v1`, then
  `git cherry-pick d6512fb 70bcd6a 18de64c` (clean), then `ab2f5f8` (resolve the docs conflict),
  then reapply `9d1478b`, `8dca96b`, `8ac99f8`, `d4efb92` **by hand**, keeping everything
  `release/onsite-v1` added (replica floors, AtWork/On-site params, `entraInternalEmailDomains`).
  Check that the result matches live PROD env (§11) value for value.
- Validation: birthday-api pytest, both vitest suites, `az bicep build` on `main.bicep`, and a
  `what-if` against UAT (read-only). Diff the bicepparams against `origin/feat/onsite-dashboard-v1`.
- Approval: PR into `release/onsite-v1` needs review. No deploy in this step.

**P0-2 Set `APP_ENV=prod` on PROD `birthday-web`** (and `APP_ENV=uat` on UAT for consistency).
- Why: §7 #1. One env var; no image change.
- Command (needs approval, it's a PROD change): `az containerapp update -g rg-dijione-prod -n birthday-web --set-env-vars APP_ENV=prod`.
- Validation: `/birthday/api/meta` returns `is_production:true`; Email Safety nav absent for an admin.
- Then record it in P1-2 so it isn't ad hoc.

### P1 — Required completion work

**P1-1 Release invitation workflow + deep-link email to UAT, then PROD.** Build from the reconciled
branch; deploy `birthday-api` **and** `migrate-birthday-api` with the same digest, run migration
(`ad84ec92abcb`), then `birthday-web` and `birthday-supplier-web`. Validate in UAT (simulated mail):
invite flow, readiness refresh, email body link. PROD via `promote.sh` with approval.

**P1-2 Bring runtime config into Bicep.** Add Birthday mail params (`MAIL_TRANSPORT`, `MAIL_POLICY`,
`MAIL_SHARED_MAILBOX`) per env, and a `commonWebEnv` (`APP_ENV`, optionally `RELEASE_DATE`) for
`kind=='web'`. Values must equal live (§8 table). Validate with `what-if` showing **no** change to
live env. Approval needed for any deploy.

**P1-3 Close the dev-route exposure.** In `apps/birthday-api/app/api/routes/internal.py`, add
`require_non_production` to `dev_inject_inbound_email`; in `apps/birthday-supplier-web/next.config.ts`,
narrow the `internal/dev` rewrite to the two persona paths. Add tests. Small PR.

**P1-4 PROD live-send validation** per §10, only when a genuine order exists; re-verify Exchange scope first.

### P2 — Validation / hardening
- Read-only check of PROD `alembic_version` (expect `ab10ac1cdce1`) before P1-1 migration.
- Postgres-backed test run (`pg` CI job) on the reconciliation PR.
- Tests for web `APP_ENV`/is_production gating and dev-route 404s in prod.
- Update `docs/platform/DIJIBIRTHDAY-CURRENT-STATE-HANDOVER.md` header to point at this doc.
- Re-target Birthday Dependabot PRs after reconciliation.

### P3 — Deferred
- Real inbound supplier-mail ingestion in PROD (needs a product decision + Graph app credentials).
- Default-branch hygiene (`main` vs `release/onsite-v1`) — repo-owner decision.

---

## 18. MacBook continuation instructions

```bash
cd "/Volumes/SD_APFS/Diji Projects/DijiOne/dijione-platform"
git status --short            # must print nothing; if not, stop and ask before stashing anything
git fetch --all --prune
git switch docs/birthday-handover 2>/dev/null || git switch -c docs/birthday-handover --track origin/docs/birthday-handover
git pull --ff-only
git log --oneline -3          # expect handover commit(s) on top of ab2f5f8
git rev-parse origin/release/onsite-v1   # integration branch; was 6e20849 on 2026-11-13
```

- **Authoritative for Birthday code:** `origin/feat/onsite-dashboard-v1` @ `ab2f5f8` (+ this docs branch).
- **Authoritative integration target:** `origin/release/onsite-v1`. Start new Birthday work as in P0-1
  (`chore/birthday-reconcile-release` from `origin/release/onsite-v1`). Don't commit Birthday work
  onto `feat/onsite-dashboard-v1` any more; it's an On-site feature branch whose On-site content was
  already re-applied elsewhere.
- **Avoid:** `main` (stale), Dependabot branches, any `local/*` / `pr-43` branches, the TalentFlow/platform PR chains (#79–#91).
- **Pull/rebase:** fast-forward only. Don't rebase shared branches.
- **Environment:** Python 3.12 venv per `docs/platform/local-development.md` (macOS section from #78);
  `npm ci` at the repo root; backend tests run on SQLite by default; Postgres for the `pg` job.
  `az login` to "Dijital Team IT Production" for read-only checks; Exchange checks need
  `Connect-ExchangeOnline`. `gh` CLI for PRs.
- **Clean-tree proof before work:** `git status --short` empty, `git stash list` reviewed,
  `git log origin/<branch>..HEAD` empty.
- **Never** auto-merge, push to `release/onsite-v1`/`main`, run `deploy.sh`/`promote.sh`, or
  `az containerapp update` without explicit approval. Before any ad-hoc `--image` update, read
  `deploy/README.md` (MAIL_* wipe, migrate-job image, web `APP_ENV`).

---

## 19. Related documents

- `docs/birthday/requirements.md`, `end-to-end-workflow.md`, `phase-1-definition-of-done.md`, `test-scenarios.md`
- `docs/birthday/email-safety.md`, `docs/platform/email-architecture.md`
- `docs/birthday/supplier-onboarding-runbook.md`, `docs/platform/birthday-supplier-authentication.md`
- `docs/platform/DIJIBIRTHDAY-CURRENT-STATE-HANDOVER.md` (2026-09-09 snapshot)
- `deploy/README.md` (ad-hoc update hazards), `deploy/promote.sh`

No secrets appear in this document. Values shown are resource names, digests, app/object IDs and
non-secret env vars; secret values were redacted at collection time.

---

## 20. Reconciliation addendum (2026-11-13, branch `chore/birthday-reconcile-release`)

Built from `origin/release/onsite-v1` @ `6e20849`. Supersedes §2's "only on
feat/onsite-dashboard-v1" table, §17 P0-1/P1-2/P1-3, and corrects §17 P1-1's ordering.

| Handover item | State on this branch |
|---|---|
| `d6512fb` `70bcd6a` `18de64c` `ab2f5f8` | Cherry-picked; Birthday app/package source is byte-identical to `ab2f5f8` |
| `9d1478b` `8dca96b` `8ac99f8` `d4efb92` | Reapplied by hand on top of release (replica floors, `entraInternalEmailDomains`, AtWork/On-site/TalentFlow params kept) |
| PROD/UAT Entra, supplier URLs, integration modes, mail | In bicepparams; read-only `what-if` against live DEV/UAT/PROD shows **no change** for any of them |
| `birthday-web` `APP_ENV` (§7 #1) | Declared in `main.bicep`; `/api/meta` now also fails closed (unset ⇒ production) |
| `RELEASE_DATE` (§7 #2) | `releaseDates` param + `deploy/release-dates.sh` carry-forward wrapper |
| Dev-route exposure (§7 #4) | Injector requires `APP_ENV=development`; supplier-web rewrites only the two persona paths |
| **New:** custom domains not in IaC | `customDomains` param declares the six live bindings; a full `main.bicep` run would otherwise have removed them |

**Corrected deployment order for `ad84ec92abcb`.** The migration is additive
(old API works on the new schema; the new API breaks every `SupplierUser`
query on the old schema). So: update `migrate-birthday-api` to the new digest
→ run it and confirm `alembic_version = ad84ec92abcb` → `birthday-api` (same
digest) → `birthday-web` → `birthday-supplier-web`. A full `main.bicep` run sets
both images from one `imageDigests`, but the migration still has to finish before
API traffic; for an ad hoc rollout, follow the order above.

**Found outside Birthday by the same `what-if` (not changed here):** PROD and DEV
`talent-api` would lose live `EXTERNAL_PORTAL_BASE_URL` (no `externalPortalBaseUrl`
in those param files); DEV `recruitment-api` `minReplicas` 1 → 0; `shell-web`
gains the On-site/AtWork upstream URLs. These belong to their owning modules.
