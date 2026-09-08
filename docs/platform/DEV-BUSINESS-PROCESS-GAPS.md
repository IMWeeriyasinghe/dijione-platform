# DijiOne DEV — business-process gap register

Maintained as hosted Azure DEV is exercised against real business processes.
Last reviewed: 2026-09-08 (DEV current-scope completion pass).

Categories:

1. **MUST FIX before DEV current-scope complete** — resolved in this pass.
2. **Approved current-scope improvements** — small, safe, in scope.
3. **Business decisions required** — safe current behaviour + the choice needed.
4. **Future enhancements** — backlog, do not block DEV.
5. **UAT/PROD considerations** — explicitly NOT actioned.

---

## 1. MUST FIX before DEV current-scope complete — RESOLVED

| # | Finding | Fix | Commit |
|---|---|---|---|
| 1.1 | `platform-api /health/deep` reported `auth_mode:"dev"` while `AUTH_MODE=entra` — it derived the value from the legacy `dev_identity_mode` flag, which an Entra env never sets. Misleading operational diagnostic. | Report `settings.auth_mode` directly; add `dev_login_enabled`. Regression test added. | `69f1e16` |
| 1.2 | 10 Phase-3 mock employees (`@example.com`, `bhr-10##`) + 8 matching `REQUIRES_ATTENTION` birthday orders persisted in `people_dev` / `birthday_dev` after the real BambooHR integration went live — polluted the People directory and birthday detection. | Guarded, Postgres-only data migrations `people-api 0002_people_drop_mock` and `birthday-api c4f6a8b0d2e4_drop_mock_orders` (count ≤ 25, `@example.com` / `bhr-10` prefix only, no-op on SQLite). People count 347 → 337, mock 0; birthday orders 8 → 0. Post-cleanup People sync re-run: 0 created, idempotent. | `6e7a9bb` |
| 1.3 | The bootstrap SUPER_ADMIN (`madushanka.weeriyasinghe@dijitalteam.com`, id 6) had no `user_module_roles`, so on login the app launcher was empty and neither DijiTalentFlow nor DijiBirthday could be exercised by a real user. | One-time DEV bootstrap grant: `talent-flow / TA_MANAGER` + `birthday / BIRTHDAY_ADMIN` (unscoped). Every other user follows the normal Admin-Centre entitlement flow. | (DB, no code) |

Earlier-phase P0/P1 defects (session-token 500 in Entra mode, `varchar(255)` truncation in recruitment-api and talent-api against real Lever data) were found and fixed during Phase 4 — see `AZURE-PHASE-4-REPORT.md` / commits `8ba0613`, `b1ac89f`, `af403ef`.

## 2. Approved current-scope improvements

None outstanding. The DEV environment holds real Lever + BambooHR read models,
the full Lever→TalentFlow→canonical-client chain resolves, and the scheduled
syncs keep it fresh.

## 3. Business decisions required

### 3.1 Lever posting tagged `DTC - National Tech`

- **Situation.** Recruitment Source holds a real, active Lever posting
  (`L3 Engineer`, provider id `c3120a05-2b78-41f9-baca-38411bbf6f82`) carrying a
  single, well-formed governed tag `DTC - National Tech`. There is **no**
  canonical `Client` named "National Tech" among the 28 DTC organisations.
- **Current safe behaviour.** `PostingClientMapping` stays `UNMAPPED /
  UNKNOWN_CLIENT_IDENTIFIER`. The posting is **not** client-visible, no
  `Client` row is auto-created, no fuzzy match is attempted. Fail-closed, per
  the governed-tag contract (CLAUDE.md §4a).
- **Choices.**
  a) *Legitimate new client/prospect* — a platform admin adds "National Tech"
     as canonical master data (Admin Centre → Organisations); the next
     reconcile resolves it to `VERIFIED`.
  b) *Tag error* — TA corrects the Lever posting tag to the actual canonical
     client name; the next reconcile resolves it.
  c) *Dormant / historical posting* — leave as-is.
- **Recommendation.** TA confirms whether National Tech is a current client.
  If yes → (a). If it should map to an existing client → (b). Do **not**
  silently create it.
- **Consequence of leaving it unchanged.** Exactly one posting (and any
  candidates attached to it in Lever) never becomes visible to a client —
  safe, but that client cannot see their pipeline in the portal.

### 3.2 No client-visible applications / magic-link grants yet

- **Situation.** The reconcile promoted 33 `VERIFIED` postings into 33
  `TalentRequests` (SOURCING) with 52 candidates / 52 applications. Every
  application is `is_client_visible = false` (the correct default — TA marks
  visibility explicitly) and there are 0 `magic_link_grants`.
- **Current safe behaviour.** The external TalentFlow portal returns
  `401` for every data route without a redeemed session, and a bogus/expired
  token → `401 "This access link is invalid or has expired"`. Nothing leaks.
- **Choice / recommendation.** For a full external-portal walkthrough with
  live data, a TA (e.g. the SUPER_ADMIN acting as `TA_MANAGER`) should, for
  one real request: mark an application client-visible, then issue a
  client-access magic link and redeem it. This is a normal TA workflow, not a
  defect; it just hasn't been performed in DEV yet.
- **Consequence of leaving it unchanged.** The external client-review path is
  proven only by the automated suite (`talent-api` tenant-isolation /
  magic-link tests) and the negative hosted checks, not by a live redeemed
  session.

### 3.3 `client_external_ids` crosswalk is empty

- **Situation.** `platform_dev.client_external_ids` (canonical client ↔
  external provider id) has 0 rows. DTC resolution works by exact
  `Client.name` match instead, which is the approved path (§4a).
- **Recommendation.** No action unless a provider-id-based crosswalk becomes
  a requirement (e.g. HubSpot commercial data). Document only.

## 4. Future enhancements (backlog — do NOT block DEV completion)

| # | Item |
|---|---|
| 4.1 | Correlation IDs are not surfaced in hosted Log Analytics at the current INFO / uvicorn-access level (middleware works; response header carries `x-correlation-id`). Structured logging would make cross-service tracing possible. |
| 4.2 | No real employee birthday fell inside the current forward detection window, so no positive `BirthdayOrder` has been demonstrated end-to-end against real People data (the mechanism is proven — scan COMPLETED, idempotent, consumes `people-api`). Widening the detection window config for one run would show a positive. |
| 4.3 | No supplier catalogue is seeded in `birthday_dev`, so detected orders stop at `REQUIRES_ATTENTION / NO_SUPPLIER` (correct fail-closed). Supplier + catalogue fixtures are needed for a full birthday dispatch E2E. |
| 4.4 | `admin-api /health/deep` reports `status:"degraded"` when a downstream (talent-api) is scaled to zero — it recovers to `healthy` once warm. Cosmetic; could distinguish "cold" from "down". |
| 4.5 | `talent-api /health/deep` shows `recruitment_source:"degraded"` on a cold `recruitment-api` — by design a Recruitment Source outage must not deregister talent-api (`status` stays `healthy`), so this is expected, not a bug. |

## 5. UAT / PROD considerations — NOT ACTIONED

Recorded for a later, explicitly-approved UAT decision. **None of this has been
started.**

- `dijione-uat` Entra app registration with UAT reply URLs (a new registration).
- `deploy/bicep/main.uat.bicepparam`: `authMode=entra`, UAT tenant/appId/
  `publicBaseUrl`, provider modes (likely `mock` first), `seedDevIdentities=false`,
  `seedTalentClientExtensions=true`.
- `rg-dijione-uat` foundation (`foundation.uat.bicepparam`) + `init-secrets.sh` +
  UAT Key Vault secrets (`entra-client-secret-uat`, and UAT-scoped provider
  keys if going live).
- Promote the exact DEV image digests to UAT (build once / promote by digest).
- Real outbound email, HubSpot / `commercial-api`, `spark-api`, production DNS —
  all remain deferred.
