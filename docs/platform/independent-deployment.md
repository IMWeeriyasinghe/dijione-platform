# DijiOne independent module deployment

Status: proposal for review. Nothing here is implemented yet.

**Principle:** independent application releases, controlled shared-platform
releases, and no unintended cross-application deployment dependencies.

The monorepo, Azure Container Apps and the existing registries stay. No new
Azure service is needed.

## 1. Rules

1. A module release builds, tests, deploys and reverses only that module's apps.
2. A module release never updates a shared app. Shared apps have their own release.
3. A shared app is only replaced by an image whose source contains the source of
   the image currently running there.
4. Every deployment is by digest and records its commit, digests and previous digests.
5. A migration belongs to one service and database, and ships with that service.
6. Digests are rechecked immediately before deployment, because other streams
   share each environment.

## 2. Ownership

| Unit | Apps | Jobs | Database | Release owner |
|---|---|---|---|---|
| **Platform (shared)** | `shell-web`, `platform-api`, `admin-api`, `admin-web` | `migrate-platform-api`, `migrate-admin-api` | platform, admin | Platform |
| Shared packages | `design-system`, `auth-client-*`, `contracts` | n/a | n/a | Platform; consumed at build time |
| Shared infrastructure | Environment, registries, PostgreSQL server, Key Vault, DNS | n/a | n/a | Platform |
| **TalentFlow** | `recruitment-api`, `talent-api`, `talent-web`, `talentflow-portal-web` | `recruitment-sync-job`, `talent-reconcile-job`, `migrate-talent-api`, `migrate-recruitment-api`, `bootstrap-talent-clients` | talent, recruitment | TalentFlow |
| Birthday | `birthday-api`, `birthday-web`, `birthday-supplier-web` | Its own | birthday | Birthday |
| On-site | `onsite-api`, `onsite-web` | Its own | onsite | On-site |
| AtWork | `atwork-api`, `atwork-web` | Its own | atwork | AtWork |
| People source | `people-api` | Its own | people | Platform; consumed by modules through its API |

Gateway routes live in `shell-web`. A new module's routes are a platform change.

## 3. Pipeline

Add a manifest per module, `deploy/modules/<module>.yaml`:

```yaml
module: talentflow
apps: [recruitment-api, talent-api, talent-web, talentflow-portal-web]
order: [recruitment-api, talent-api, talent-web, talentflow-portal-web]
jobs_pause: [recruitment-sync-job, talent-reconcile-job]
migrations: [talent-api, recruitment-api]
health: [recruitment-api, talent-api]
min_platform: { routes: ["/talent-flow", "/api/talent"], auth_mode: entra }
```

`deploy/deploy-module.sh <module> <env> <commit>` runs these stages:

| # | Stage | Fails when |
|---|---|---|
| 1 | Resolve apps from the manifest | The app is outside the manifest or is shared |
| 2 | Require CI success for that commit's module checks | Any module check failed |
| 3 | Build only those apps from a clean export; never reuse a dirty tree | Tag exists with another digest |
| 4 | Capture digests and write a release record | Digest missing |
| 5 | Check health, migration heads and `min_platform` | Revision or route mismatch |
| 6 | Recheck current digests; save them as the rollback set | Current differs from the reviewed plan |
| 7 | Run `az containerapp update --image <digest>` per app | Any new revision is unhealthy |
| 8 | Smoke tests | Any failure triggers stop and rollback decision |
| 9 | `--rollback <record>` restores that record's digests | n/a |

CI: keep the current path-filtered workflows and add a required
`module-release` summary per module, so an unrelated module's red check does not
block a release. Add `workflow_dispatch` only after the script is proven.

Platform releases use the same script with `--platform`, which also requires:

- explicit approval;
- the ancestor check in section 4;
- build and smoke tests for affected consumers.

## 4. Shared-platform policy

- **Provenance:** every shared image is tagged with its commit. The release record
  lists commit, digest, environment, approver and date.
- **Downgrade guard:** before replacing a shared app, find the running image's
  commit and require `git merge-base --is-ancestor <running> <candidate>`.
  This stops an older feature-branch shell removing newer routes.
- **Compatibility:** modules declare `min_platform`. Shared changes are additive by
  default. A breaking change needs a deprecation period and consumer sign-off.
- **Consumers:** a package change runs lint, tests and build for all consumers.
- **Packages at build time:** a module image keeps the package versions it was
  built with, so a module release needs no shared deployment.
- **Regenerated routes:** shell routes come from `next.config.ts` at build time, so
  adding a module requires a platform release of `shell-web`.

## 5. Git and release

- Module branches: `<module>/<topic>`. PRs touch one module wherever possible.
- Shared changes: `platform/<topic>`, separate PR, targeting the platform baseline.
  Never bundled into a module PR.
- When the base advances: review changed shared files and deployed shared digests.
  Rebase or merge only if the module needs the change, never just to deploy.
- A module may deploy from its own branch **only** for module-owned apps.
- Release identity: `<module>-v<version>` tag on the source commit, plus the
  release record.
- Windows and macOS: one remote as source of truth; each machine works in its own
  branch or worktree; fetch before starting and before any release; never deploy
  from an uncommitted tree; use `.gitattributes` for line endings.
- Rollback: redeploy the recorded digests. Data changes follow the module's
  runbook, because images do not reverse data.

## 6. Impact on existing scripts and resources

| Item | Today | Change |
|---|---|---|
| `deploy.sh` | Builds a fixed core set plus options, then deploys full foundation and workloads Bicep | Keep for first bring-up only; block for routine releases |
| `main.bicep` | Full deployment can reset domains and ad hoc settings | Not used for module releases |
| `build-images.sh` | Always includes shared apps; reads the working tree; skips existing tags | Add manifest selection and clean-export check |
| `promote.sh` | Imports one digest set for the whole platform | Add per-module import from release records |
| `Dockerfile.web` | Gateway URLs baked at build | Keep; a platform-release concern |
| Scheduled jobs | Reference app images but only `curl` | No change; optional pause support |
| Azure resources | Per-app Container Apps already allow independent updates | None |
| Branch protection | Not available on the current GitHub plan | The script's checks enforce the rules |

## 7. Work required

1. Module manifests.
2. `deploy-module.sh`, with guard, release records and rollback.
3. Selection flag and clean-export check in `build-images.sh`.
4. Per-module promotion.
5. Commit provenance in API images; only web images embed it today.
6. `module-release` CI summaries.
7. Shared-release procedure and a first record of current shared digests.
8. Later: an Azure federated identity if releases move to GitHub Actions.
