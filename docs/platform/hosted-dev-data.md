# Hosted DijiOne DEV — data policy

What a **hosted** DijiOne environment (DEV / UAT / PROD) is and is not
allowed to contain, and how the local `bootstrap-dev.sh` concept is split
for hosting. Local development is unaffected — keep using
`scripts/bootstrap-dev.sh` (`npm run dev:all` / the deterministic tooling).

## The three layers

| Layer | Script | Hosted DEV | Contains |
|---|---|---|---|
| **MIGRATE** | `scripts/db-migrate.sh` | **yes** | `alembic upgrade head` per DB-owning service, each against its own alembic tree. Schema + the migration-seeded RBAC catalog + module registry + the platform-owned canonical Client master set. No business data. |
| **DEV IDENTITY BOOTSTRAP** | `scripts/dev-identity-bootstrap.sh` → `platform-api/scripts/seed.py --identity-only` | **optional** | The 5 staff dev-login personas (`madushanka-ta`, `customer-success`, `ta-manager`, `platform-admin`, `super-admin`) + their platform/module-role assignments, so `AUTH_MODE=dev` persona switching works for internal authorization testing behind the Easy Auth gate. **No** canonical Client seed, **no** `ta-portfolio` demo persona (needs client rows, demonstrates a feature). A hosted environment may instead create real users through the Admin Center. |
| **BUSINESS DATA** | *(none — never seeded)* | **never** | TalentRequests, candidates, applications, interviews, messages, documents, and client rows treated as business records. These originate only from: **Recruitment Source → controlled Lever GET-only sync → canonical organisation reconciliation → TalentFlow projections / workflow state** (Amendment 1's staged provider-data model). |

`scripts/bootstrap-dev.sh` (migrate + the *full* demo seed, including
`ta-portfolio` and the talent-api client-extension mirror) is **LOCAL
DEVELOPMENT ONLY** and carries a header saying so. Do not run it, or any
bare `scripts/seed.py` without `--identity-only`, in a hosted environment.

## DECIDED 2026-09-04 — canonical Client master set in hosted environments (Option A, final)

`MIGRATE` runs `alembic upgrade head`, which includes platform-api's
migration **`h8i9j0k1l2m3_real_dev_client_reconciliation`**. That migration
`bulk_insert`s the **28-client canonical set** (`app.core.real_dev_clients.REAL_DEV_CLIENTS`
— real DTC-tagged names captured from a real GET-only Lever discovery run,
2026-09-01).

**Resolution — Option A (accepted by the platform owner):** the 28 canonical
Client / Organisation rows are **permanently platform-owned master / reference
data** (data-ownership contract §2a), seeded by that one migration in **every**
hosted environment — DEV, UAT and PROD. They are **not** fictional TalentFlow
business records; the names are real.

Still prohibited as seed data in any hosted environment (unchanged): `TalentRequest`,
`Candidate`, `Application`, `Interview`, `Message`, `Document`, and any
fabricated provider-derived record. Those originate only from the controlled
Recruitment Source / Lever GET-only sync + canonical-organisation reconciliation.
`scripts/dev-identity-bootstrap.sh` still adds **no** clients and **no** business
data.

`scripts/db-migrate.sh` runs this migration as part of `alembic upgrade head`
and states the decision in its header. Option B (gating the seed behind a flag)
was considered and **rejected** — it would alter an already-applied migration's
behaviour and needs a reconciliation path that does not exist.
