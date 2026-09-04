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

## Open architecture question — canonical Client master set in hosted DEV

`MIGRATE` runs `alembic upgrade head`, which includes platform-api's
migration **`h8i9j0k1l2m3_real_dev_client_reconciliation`**. That migration
`bulk_insert`s the **28-client canonical set** (`app.core.real_dev_clients.REAL_DEV_CLIENTS`
— real DTC-tagged names captured from a real GET-only Lever discovery run,
2026-09-01).

- The **data-ownership contract §2a** treats the canonical Client /
  Organisation set as *permanently platform-owned master data*, seeded by
  *one migration, no interim registry*. By that reading the 28 rows are
  **reference data** and belong in `MIGRATE`.
- **Amendment 3** ("no fictional TalentFlow business data in Azure DEV";
  clients should originate from the controlled Lever sync + canonical org
  reconciliation) can be read as wanting hosted DEV's canonical Client set
  to **start empty** and be built by that flow.

These pull in opposite directions and this is an **architecture decision
for the platform owner**, not something Phase 0 resolved:

- **Option A — accept the migration seed.** The 28 canonical Client rows
  are platform-owned master/reference data (contract §2a). Hosted DEV gets
  them from `alembic upgrade head`. `dev-identity-bootstrap.sh` still adds
  no clients; `BUSINESS DATA` is still never seeded. Simplest; matches the
  established contract; the names are real, not invented.
- **Option B — gate the seed.** Add a parameter / env flag to
  `h8i9j0k1l2m3` (and a matching guard in `seed_canonical_clients`) so
  hosted DEV can run `alembic upgrade head` **without** the 28-row insert,
  and build the canonical set later via controlled Lever discovery + a
  canonical-organisation reconciliation step. Larger change; touches an
  already-applied migration's behaviour; needs a reconciliation path that
  does not exist yet.

Until this is decided, `scripts/db-migrate.sh` runs the migration **as-is
(Option A)** and says so in a comment. Flag this in the next planning
review.
