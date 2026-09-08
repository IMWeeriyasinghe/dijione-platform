# DijiOne — Azure DEV current-scope completion report

Consolidated status of the hosted Azure DEV environment against the approved
current product scope. This is **not** a UAT/PROD task — DEV is now the
environment for continued business-process testing.

Date: 2026-09-09 · Branch `local/azure-dev-prep` · HEAD `3982034`

---

## 1. Executive status

Hosted Azure DEV is a stable, secure, realistic environment representing the
approved current scope. Real Microsoft Entra internal authentication is live;
Lever (Recruitment Source) and BambooHR (People) run as controlled
read-only integrations with scheduled syncs firing automatically and
idempotently; the full governed **canonical org → TalentFlow client extension →
Lever `DTC -` tag → Recruitment Source posting → PostingClientMapping →
TalentRequest → Candidate/Application** chain resolves against real data
(33 VERIFIED, fail-closed for the rest). Four current-scope defects were found
and fixed in this pass (including the broken hosted login screen); Phase-3
mock data was cleaned via controlled migrations. 570 automated tests pass. No unintended public ingress, no
cross-service DB access, no provider write capability. One business decision
(National Tech) is documented and safely unresolved.

**Verdict: DIJIONE DEV — CURRENT SCOPE COMPLETE** (see §23).

## 2. Exact branch / commit

- Branch: `local/azure-dev-prep` (local only — GitHub remote freeze in force).
- HEAD: `67d147f` (docs) — code HEAD `3982034` `fix(dev): show the Microsoft sign-in view when AUTH_MODE=entra`.
- New local commits this pass: `6e7a9bb` (mock-data cleanup migrations),
  `69f1e16` (health auth_mode fix), `f985cad` (these docs), `3982034`
  (Entra sign-in screen). Prior Phase-4 commits `b2e8d58 … 8c2b800`
  unchanged.

## 3. Azure DEV deployment state

- Subscription `7d97cf51-…` "Dijital Team IT Production", tenant `2abce006-…`,
  principal `sa-paymentslip@dijitalteam.com`.
- `rg-dijione-dev`: 12 Container Apps (all `Succeeded` / `Running`, `min0/max1`,
  `0.25` vCPU / `0.5Gi`), 11 Jobs, `psql-dijione-dev` (B1ms Burstable, private,
  HA off, PG 16 — Ready), `kv-dijione-dev`, `cae-dijione-dev`, `id-dijione-dev`,
  VNet + private DNS.
- ACR `crdijionenonprod` (`rg-dijione-shared`, Basic) — 12 `dijione/*` repos.
- Public ingress: `shell-web`, `talentflow-portal-web`, `birthday-supplier-web`
  only. The other 9 apps `external=false` (`*.internal.*`).
- Jobs: 5 `migrate-*`, `bootstrap-identity`, `bootstrap-talent-clients`,
  `recruitment-sync-job` (`0 */6`), `talent-reconcile-job` (`15 */6`),
  `people-sync-job` (`0 5`), `birthday-scan-job` (`30 5`).
- `/health/deep` on all 6 APIs → `200` (see §6/§13).

## 4. Deployed image digests

| Service | Commit | Digest |
|---|---|---|
| platform-api | `69f1e16` | `sha256:5b81fe386d680a6e7d26e0750a4ce05317aa9b2c191f916262e56e8463c77822` |
| talent-api | `af403ef` | `sha256:a0fcbb5a148526de1703bdbfafc8eba1e979d1b9563fae92ae448c6913154531` |
| recruitment-api | `b1ac89f` | `sha256:51c933eb310b6cff08d02b4d2de7cbb6e85086bb862bdd5eb7afb6b3c45e3a67` |
| people-api | `6e7a9bb` | `sha256:953a438de650c2191ede5ec802110c34d8bedc5319b4792e5fbe399a8f488795` |
| birthday-api | `6e7a9bb` | `sha256:0e1fccc1e6eebd5d6a90a1b067ffaf85b96825bff1aee70b88d1362dae14c464` |
| admin-api | `2baa15d` | `sha256:2f82f743c28aaba97124ee757bebf9d4b77dd1c92a864ae201dee28d2f6b3d14` |
| shell-web | `3982034` | `sha256:6f62fd3d2290d67dca7fae429f961c7e9762a8c358875dd96cfa4d418ca77bef` |
| admin-web | `3982034` | `sha256:5b31482e5886e2d60b98b4ccb94296f3e0181472e40f2f04c2ee5ca91878197d` |
| talent-web | `3982034` | `sha256:9b107aec33a57445153cb82c6d486b742e5330fb3ebaa2972213d6209bdc72ac` |
| talentflow-portal-web | `fc1bac8` | `sha256:497b43ff676feb03448ac20bd7d6388f507371ebe1530319a63cb83c75b4773f` |
| birthday-web | `3982034` | `sha256:b555b230973ef8ab28b95ebc10071e232696cc22064c979645c62bec379f3b75` |
| birthday-supplier-web | `fc1bac8` | `sha256:0230aa165ecf0784e90cd03939074824c694f348b0685d7a6c5dcab274f287ee` |

Map: `scratchpad/imagedigests-phase4.json`.

## 5. Database / migration state

All 5 domain databases at head (confirmed by `/health/deep` `up_to_date:true`):

| DB | Head revision |
|---|---|
| `platform_dev` | `h8i9j0k1l2m3` |
| `talent_dev` | `b3c5d7e9f1a2` (widen Lever-projected text) |
| `recruitment_dev` | `0002_widen_free_text` |
| `people_dev` | `0002_people_drop_mock` (this pass) |
| `birthday_dev` | `c4f6a8b0d2e4_drop_mock_orders` (this pass) |

No destructive schema change. The two new migrations are guarded data
cleanups (Postgres-only, count-capped, no-op on SQLite/CI).

## 6. Entra / authentication result

- `AUTH_MODE=entra` on `platform-api`; `/api/auth/config` → `{"auth_mode":"entra"}`;
  `/health/deep` now correctly reports `auth_mode:"entra"`, `dev_login_enabled:false`.
- Passwordless persona bypass **unavailable**: `/api/auth/dev-personas` and
  `/api/auth/dev-login` → `404`.
- `/login` → `307` to `login.microsoftonline.com/2abce006-…/oauth2/v2.0/authorize`
  with the correct `client_id`, `redirect_uri` (`…/api/auth/callback`),
  `scope=openid profile email`, `code_challenge_method=S256`.
- Real interactive sign-in confirmed earlier by the user: first login →
  auto-created inactive (403), activated as SUPER_ADMIN, second login reached
  the DijiOne home page and the Admin Centre.
- Bootstrap admin `madushanka.weeriyasinghe@dijitalteam.com` (id 6): active,
  `SUPER_ADMIN`, `identity_provider=ENTRA`; now also granted
  `talent-flow / TA_MANAGER` + `birthday / BIRTHDAY_ADMIN` so the modules can
  be exercised by a real user. Every other user follows Admin-Centre entitlement.
- Malformed / missing bearer → `401` (not `500`).
- `platform_dev.users`: 5 `DEV_IDENTITY` (retained for a one-line `authMode`
  rollback) + 1 `ENTRA`, all active.

## 7. RBAC / security result

- Internal APIs: all 9 `external=false`.
- Each API carries **only its own** `database-url-<domain>` Key Vault secret →
  no cross-service DB access is even configurable. `admin-api` (a BFF) carries
  none.
- `talent-api` and `birthday-api` carry **no** `lever-*` / `bamboohr-*` secret.
- Architecture guards pass: `test_no_direct_lever_dependency` (talent-api),
  `test_no_direct_bamboohr_dependency` (birthday-api),
  `test_lever_client_safety` (recruitment-api).
- No provider secret string in the shell-web JS bundle (grep = 0).
- Two-plane admin model intact: Admin Centre owns identity/entitlement/canonical
  clients/audit; TalentFlow module admin owns visibility/mapping/sync;
  `require_platform_admin` / `require_platform_permission` gates enforced
  (pytest); `admin-api` exposes only `/api/admin/*`.

## 8. Lever result

- `recruitment-api` `INTEGRATIONS_MODE=live`; sole owner of the Lever client.
- GET-only by construction — `LiveLeverClient` defines only `_get`; no
  `_post/_put/_patch/_delete`; 4 safety tests pass. **No Lever write occurred.**
- Read model: **663 postings, 184 candidates, 186 candidacies, 184 external
  mappings**. `recruitment_sync_runs`: the `0 */6` cron fired at 00:03 / 06:03 /
  12:03 UTC — all `SCHEDULED`, all `SUCCEEDED`, records `created` 0–6 /
  `updated` ~837 → automatic + idempotent. 0 duplicate `lever_posting_id` /
  `lever_contact_id`.

## 9. People / BambooHR result

- `people-api` `INTEGRATIONS_MODE=live`; sole owner of the BambooHR client.
  Read-only: only `POST /v1/reports/custom?format=JSON` (BambooHR's report-read
  API). No employee-mutation path. **No BambooHR write occurred.**
- After the Phase-3 mock cleanup: **337 employees, all ACTIVE, 0 `@example.com`,
  11 future starters (hire_date > today), 0 duplicate `bamboohr_id`**.
- `people_sync_runs`: the `0 5` cron ran at 05:00 UTC — `SUCCEEDED`,
  `read=336 created=0 updated=336`; a manual re-run after cleanup also
  `created=0` → idempotent, mock rows did not return.
- Employee Number kept distinct from BambooHR id (330/337 have a distinct
  `employee_number`).

## 10. TalentFlow reconciliation result

- `talent_dev.clients`: 28 extension rows, all with `platform_client_id` (from
  `bootstrap-talent-clients`).
- `recruitment_posting_refs`: 663 (projected from Recruitment Source via
  `RecruitmentSourceClient` — talent-api holds no Lever key).
- `posting_client_mappings`: 663 — **33 `VERIFIED / LEVER_DTC_TAG / RESOLVED`**
  to the exact canonical client, **1 `UNMAPPED / UNKNOWN_CLIENT_IDENTIFIER`**
  (`DTC - National Tech` — §16 / gap 3.1), **629 `UNMAPPED / NO_DTC_TAG`**,
  **0 `VERIFIED` without a client**, **0 duplicate mappings**. Idempotent on
  repeated reconcile (`15 */6` cron + manual re-runs).
- `talent_requests`: 33 (all `SOURCING`), across 28 clients, 0 duplicates by
  posting. `candidates`: 52 (all `source=LEVER`, `professional_title` up to 633
  chars — the value that previously broke `varchar(255)`). `applications`: 52,
  52 distinct candidates, 14 distinct requests, 0 duplicates, all
  `is_client_visible=false` (correct default — §16 / gap 3.2).
- Graceful degradation observed: a cold `recruitment-api` makes the reconcile
  log `recruitment-api unavailable — projection not refreshed (ReadTimeout)`
  and return `202` without corrupting the prior projection; a warm retry
  completes it.

## 11. Birthday result

- `birthday_dev` has **no employee mirror table** — Birthday consumes People
  only through `people-api` (`EmployeeDirectoryClient`); `birthday-api` holds no
  BambooHR credential and no People DB access.
- `birthday-scan-job`: the `30 5` cron ran at 05:30 UTC — `COMPLETED`.
  Idempotent (`UniqueConstraint(employee_id, birthday_year)`).
- After cleanup: **0 birthday orders**, **0 supplier communications**.
  `EMAIL_SENDING_MODE=mock` — no real email. No real employee birthday fell in
  the current forward window, so no new order was created (mechanism proven;
  §19 / backlog 4.2).
- Source-unavailable behaviour: a `people-api` outage makes the scan defer
  (`DEFERRED_SOURCE_UNAVAILABLE`, zero orders) and self-heal on the next scan
  (covered by `birthday-api` suite).

## 12. External portal result

- `talentflow-portal-web` and `birthday-supplier-web` serve `200`, independent
  of Entra (no `/login` Entra route on either).
- `POST /api/talent/external/redeem` with a bogus 64-char token →
  `401 "This access link is invalid or has expired"` (generic, no leak).
- `/api/talent/external/{dashboard,requests,applications/1}` with no session →
  `401 "Missing bearer token"`.
- Tenant isolation, client-scope-from-session, `is_client_visible` filtering,
  expired/revoked/hashed grants — covered by the `talent-api` suite (159
  passed). No live redeemed session has been exercised in DEV yet (§16 / gap 3.2).

## 13. Scheduled-job result

| Job | Trigger | Last hosted run | Result |
|---|---|---|---|
| `recruitment-sync-job` | `0 */6` | 09-08 12:03 UTC | SUCCEEDED (idempotent) |
| `people-sync-job` | `0 5` | 09-08 05:00 UTC | SUCCEEDED (idempotent) |
| `birthday-scan-job` | `30 5` | 09-08 05:30 UTC | COMPLETED |
| `talent-reconcile-job` | `15 */6` | this pass (manual + cron) | SUCCEEDED, 33 VERIFIED stable |
| `migrate-*` (×5) | Manual | this pass | SUCCEEDED, all heads current |
| `bootstrap-identity` | Manual | this pass (also used for deep-health probes) | SUCCEEDED |
| `bootstrap-talent-clients` | Manual | Phase 4 | SUCCEEDED, 28 rows |

## 14. Business-process walkthrough findings

- **Data chain end-to-end (verified at the data layer):** 28 canonical
  organisations → 28 TalentFlow client extensions → 34 well-formed `DTC -` tags
  → 663 postings → 33 `VERIFIED` PostingClientMappings → 33 `TalentRequests`
  (SOURCING) → 52 candidates / 52 applications. Fail-closed everywhere else.
  No duplicates on repeat reconcile.
- **Authenticated hosted UI walkthrough** (clicking through as Platform Admin /
  TA Manager / external client) requires the operator's interactive Entra
  session and has not been performed by the agent. The workflow and
  authorization logic is covered by 479 backend + 88 frontend automated tests;
  the unauthenticated boundaries and the data chain are verified hosted. The
  operator (now entitled to both modules) can drive the click-through directly
  — the environment is ready for it.
- **National Tech** and **no client-visible applications yet** are documented
  business-decision / TA-workflow items (`DEV-BUSINESS-PROCESS-GAPS.md` §3),
  not defects — current behaviour is safe and fail-closed.

## 15. Defects discovered and fixed during this exercise

| Sev | Defect | Fix |
|---|---|---|
| P2 | `platform-api /health/deep` misreported `auth_mode:"dev"` under `AUTH_MODE=entra` | `69f1e16` — report `settings.auth_mode`; add `dev_login_enabled`; regression test |
| P2 | 10 Phase-3 mock employees + 8 mock birthday orders polluting live People/Birthday data | `6e7a9bb` — guarded data migrations `people-api 0002` + `birthday-api c4f6a8b0d2e4` |
| P3 | Bootstrap SUPER_ADMIN had no module roles → empty app launcher, modules not exercisable by a real user | DEV bootstrap grant (talent-flow TA_MANAGER + birthday BIRTHDAY_ADMIN) |
| P1 | Hosted login screen showed the broken Dev Identity Mode persona switcher (404 "Could not load personas") under AUTH_MODE=entra — no way to sign in | `3982034` — `AuthGate` reads `/api/auth/config` and renders an `EntraSignIn` ("Sign in with Microsoft") card in entra mode; 4 web images rebuilt; regression tests |

(Phase-4 P0/P1 fixes — Entra session-token 500, two `varchar(255)` truncations
— are in `AZURE-PHASE-4-REPORT.md`.)

## 16. Regression / test results

| Suite | Result |
|---|---|
| platform-api pytest | 63 passed (incl. new `/health/deep` entra regression) |
| talent-api pytest | 159 passed |
| admin-api pytest | 13 passed |
| recruitment-api pytest | 51 passed |
| people-api pytest | 18 passed |
| birthday-api pytest | 175 passed |
| shell-web / admin-web / talent-web / birthday-web / talentflow-portal-web / birthday-supplier-web vitest | 26 / 2 / 42 / 2 / 16 / 3 = 91 passed |
| **Total** | **570 passed, 0 failed** |
| Architecture guards (no-direct-Lever, no-direct-BambooHR, Lever-safety) | pass |
| `az bicep build` / `lint` / `build-params` | clean |
| ruff (changed apps) | clean |
| Migration apply (all 5 heads, SQLite + hosted Postgres) | clean |
| Hosted smoke: auth surface, 6 frontends, both portals, 6 `/health/deep` | all green |

## 17. Known non-blocking DEV limitations

- Cold-start latency on the first request after idle (every API `min0`) — the
  accepted lean-DEV cost tradeoff; `minReplicas` was **not** raised.
- Correlation IDs not surfaced in hosted Log Analytics at INFO.
- No supplier catalogue seeded → birthday orders stop at `REQUIRES_ATTENTION`
  (correct fail-closed).
- `admin-api` / `talent-api` `/health/deep` briefly `degraded` while a
  downstream is scaled to zero (recovers when warm; by design for
  `recruitment_source`).
- Real email, HubSpot / `commercial-api`, `spark-api` intentionally inactive.

## 18. Business decisions still required

1. **`DTC - National Tech`** — is it a real client (add to canonical master), a
   tag error (fix in Lever), or a dormant posting (leave)? Currently fails
   closed. Detail: `DEV-BUSINESS-PROCESS-GAPS.md` §3.1.
2. **Exercise one external client-review flow** — a TA marking an application
   client-visible + issuing/redeeming a magic link, so the external portal path
   is proven with live data. `DEV-BUSINESS-PROCESS-GAPS.md` §3.2.

## 19. Future enhancement backlog

See `DEV-BUSINESS-PROCESS-GAPS.md` §4: hosted correlation-ID tracing;
birthday detection-window demo; supplier-catalogue fixtures for a full
birthday dispatch E2E; `/health/deep` cold-vs-down distinction for BFFs.

## 20. UAT / PROD considerations — explicitly NOT actioned

Recorded in `DEV-BUSINESS-PROCESS-GAPS.md` §5. Nothing provisioned,
configured, deployed, migrated, or promoted for UAT/PROD. No `dijione-uat`
Entra registration, no `rg-dijione-uat`, no UAT secrets, no image promotion,
no production DNS, no real email, no HubSpot activation.

## 21. Cost-profile confirmation

Unchanged lean DEV profile: 12 Container Apps `min0/max1`, `0.25` vCPU /
`0.5Gi`; PostgreSQL `Standard_B1ms` Burstable / 32 GiB / HA off; one shared ACA
Consumption environment; ACR Basic; existing Log Analytics + Key Vault. No
APIM / Front Door / AKS / Service Bus / Redis / Event Grid / extra PG / extra
ACA environment / dedicated profile / paid monitoring. The two new Manual Jobs
(`bootstrap-talent-clients`, and the migrate jobs used for cleanup) add no
recurring cost. No purchase or cost decision arose.

## 22. GitHub remote-freeze confirmation

No `git push`, no new PR, no modification of PR #71, no Actions rerun, no
remote merge, no remote branch manipulation, Dependabot PR #72 untouched. All
work is local commits on `local/azure-dev-prep` (`… → 6e7a9bb → 69f1e16 → f985cad → 3982034`).

## 23. Final DEV completion checklist

- [x] Azure DEV infrastructure healthy
- [x] all intended DEV workloads healthy (12 apps `Succeeded`/`Running`; 6 `/health/deep` → 200)
- [x] migrations current (5 heads, all `up_to_date`)
- [x] Entra authentication functional (real login confirmed; `auth_mode:entra`)
- [x] authorization / RBAC functional (Admin Centre; 479 backend tests; gates enforced)
- [x] DEV persona bypass disabled under Entra (`dev-personas`/`dev-login` → 404; `dev_login_enabled:false`)
- [x] canonical organisation model healthy (28 ACTIVE; 28 extensions)
- [x] Lever live read-only integration healthy (`live`; GET-only; sync SUCCEEDED)
- [x] Lever sync / reconciliation idempotent (scheduled cron + manual; 0 duplicates)
- [x] People / BambooHR integration healthy (`live`; 337 ACTIVE; deep health ok)
- [x] People sync idempotent (0 created on re-run; mock rows stay gone)
- [x] Birthday consumes People correctly (no mirror; no BambooHR credential; scan via people-api)
- [x] TalentFlow consumes Recruitment Source correctly (`RecruitmentSourceClient`; no Lever key; 663 refs)
- [x] TalentFlow canonical client reconciliation stable (33 VERIFIED; idempotent; 0 dups)
- [x] external TalentFlow isolation proven (401 fail-closed; tenant-isolation suite)
- [x] magic-link security proven (bogus token → generic 401; hash/expiry/revoke suite)
- [x] intended scheduled jobs healthy (recruitment / people / birthday crons SUCCEEDED)
- [x] no unintended public ingress (3 external only)
- [x] no cross-service DB / source-of-truth violations (per-domain DB secret; guards pass)
- [x] no known P0/P1 current-scope defect (3 found this pass — all fixed)
- [x] no unresolved current-scope security defect
- [x] no unresolved current-scope data-integrity defect (mock data cleaned; idempotency proven)
- [x] automated regression clean (570 passed, 0 failed)
- [x] hosted DEV smoke / regression clean
- [x] known business decisions / gaps documented (`DEV-BUSINESS-PROCESS-GAPS.md`)
- [x] DEV can be repeatedly used for continued business-process testing (real data; module-entitled admin; scheduled syncs keep it fresh)

---

DIJIONE DEV — CURRENT SCOPE COMPLETE
