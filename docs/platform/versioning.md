# DijiOne — Per-application versioning and footer build metadata

> Authoritative. Added when the footer's version/build display was
> implemented; corrected three times after review found the bump policy and
> the shared-component architecture still weren't right — most recently to
> separate **repository change** from **application release**: a monorepo
> commit is not a release, and a shared-package change is not an automatic
> release of every consumer. This document is the source of truth for how
> each application's version is defined, how it reaches the UI, and the
> rules for who may change a major version number and when an app's version
> must move at all.

## The rule, in one sentence

**Every application in this monorepo owns its own version number, and none
is exempt.** There is no shared, platform-wide DijiOne version —
`shell-web` has its own, `birthday-web` has its own,
`birthday-supplier-web` has its own, and so on. This applies equally to
externally/client-facing apps: `talentflow-portal-web` (the external
Client Talent Review Workspace) owns and displays its own version/build
identity too — being client-facing is not grounds for an exemption.

Independent versioning does **not** mean every app must always show a
numerically different version. Two apps landing on the same number at the
same time (e.g. `DijiBirthday v1.0.1` and `DijiTalentFlow v1.0.1`) is
perfectly valid **if each independently reached that version through its
own release history** — never invent a different number just to make two
apps look distinct, and never avoid a bump just because it would make two
numbers match.

## Where an app's version lives

Each app's version is the `"version"` field in **that app's own**
`package.json` — nowhere else. This is the one, sole authoritative source
per app; no second file (e.g. an `app-version.json`) is introduced.

```
apps/shell-web/package.json               "version": "1.0.1"
apps/admin-web/package.json                "version": "1.0.1"
apps/talent-web/package.json               "version": "1.0.1"
apps/talentflow-portal-web/package.json    "version": "1.0.1"
apps/birthday-web/package.json             "version": "1.0.3"
apps/birthday-supplier-web/package.json    "version": "1.0.1"
```

(As of round 4: `birthday-web` is ahead of the others precisely because it
was the only app actually released in rounds 3 and 4 — exactly the
independent, per-app history this document describes, not a typo.)

(`apps/*-api` backend services are not currently in scope for this
mechanism — this convention covers the six Next.js frontends, which is
where the footer lives. If a backend service ever needs the same treatment,
extend this same pattern rather than inventing a second one.)

## How the value reaches the UI

Three lines are shown per app, each a distinct concept, in the existing
footer area (the bottom of that app's sidebar, or — for the two
header-shell apps, Supplier Portal and the TalentFlow Client Portal — a
footer bar at the bottom of the page):

```
DijiBirthday · by Dijital Team
v1.0.2 · Build 9ea594ddd113
Released 2026-09-14
```

| Line | Value | Source | Evaluated when |
|---|---|---|---|
| 1 | App name | Hardcoded per shell (`appName` prop) | — |
| 2 | Version + the exact commit the artifact was built from | `package.json` `"version"` (build-time) + `GIT_SHA` (Docker build arg) | Image build time, baked into `NEXT_PUBLIC_*` |
| 3 | The real release/deploy date, or omitted entirely if unavailable | `RELEASE_DATE`, an app-specific **runtime** env var | Container **runtime**, read fresh per request — never baked at build time |

### "Built" vs. "Released" — genuinely different mechanisms, not just different words

The commit/SHA line is labeled **"Build"** — it identifies the artifact.
The date line is labeled **"Released"** — it identifies when *this specific
deployment* actually happened, which can be later than the build (an image
can be built once and promoted to another environment afterward without
rebuilding — `deploy/promote.sh`'s whole purpose). Conflating the two would
misrepresent when something was actually released, so they are sourced
differently on purpose:

- **Build info (version + SHA) is a build-time constant** — `NEXT_PUBLIC_*`,
  baked into the client bundle by `next build`, identical for the lifetime
  of that image regardless of where/when it's deployed.
- **Release date is a runtime value, read per app** — see "Per-app
  `RELEASE_DATE`" below. If it isn't wired up for a given app yet, the
  footer simply omits the third line entirely; it is never fabricated from
  `BUILD_DATE` or any other stand-in.

### Per-app `RELEASE_DATE` — why a build-time value can't be used

`RELEASE_DATE` must be genuinely **per-application** — Azure Container Apps
environment variables are already scoped per service, so setting it via
`az containerapp update -n birthday-web --set-env-vars RELEASE_DATE=<...>`
touches only that one app; every other app's environment (including its
own future `RELEASE_DATE`) is untouched by construction. **A single global
value written identically into every service by one `main.bicep` run is
explicitly rejected** — that would make every app appear newly released
even when untouched.

It also can't be read the way `NEXT_PUBLIC_*` values are (a plain
`process.env` access baked at `next build` time), because deploy always
happens *after* build — reading it at build time would freeze whatever
value happened to be present then, or nothing at all. And a plain
`process.env` read inside a page/layout component isn't automatically
"read fresh per request" either: most of this app's routes are statically
prerendered (confirmed via this app's own `next build` output — most
routes show `○ (Static)`), so Next could bake a build-time snapshot of a
layout that reads `process.env.RELEASE_DATE` directly, silently defeating
the mechanism the first time a route happens to be statically optimized.

**The mechanism actually used (`birthday-web`, round 3):** a dedicated
Route Handler, `apps/birthday-web/src/app/api/meta/route.ts`, exporting
`export const dynamic = "force-dynamic"` — this is the provable guarantee
(confirmed in the app's own build output: `/api/meta` is listed as
`ƒ (Dynamic)`, never static) that it executes fresh against the running
standalone Node server (`output: "standalone"`) on every request, reading
`process.env.RELEASE_DATE` live. It's served at `/birthday/api/meta` (this
app's own `basePath`) — a client-side `fetch()` is **not** basePath-aware
the way `next/link`/`router.push` are, so the bare path `/api/meta` would
resolve to the wrong origin/path once reached through the DijiOne shell
(`https://shell-host/api/meta` instead of the correct
`https://shell-host/birthday/api/meta`) and silently 404 — confirmed by
reading `shell-web`'s rewrite table (`/birthday/:path*` is a genuine
wildcard forwarding any subpath, including `/birthday/api/meta`, straight
to `birthday-web`). The app's shell (`birthday-shell.tsx`) fetches this
once on mount and passes the result to `VersionFooter` as `releaseDate`.

This pattern is documented here for the other 5 apps to adopt on their own
future release, each substituting its own `basePath` — not built for them
in this round (a Birthday-only release; see below).

### The mechanism, end to end

1. **`deploy/Dockerfile.web`** declares `ARG GIT_SHA=unknown` and
   `ARG BUILD_DATE=unknown`, set as `ENV` before the `npm run build` step of
   the build stage (never carried into the run stage — multi-stage builds
   don't leak `ENV` across `FROM` boundaries, so nothing about this touches
   the running container's environment).
2. **`deploy/build-images.sh`** and **`deploy/build-push.sh`** compute
   `GIT_SHA` (`git rev-parse --short=12 HEAD`, overridable) and `BUILD_DATE`
   (`date -u +%Y-%m-%dT%H:%M:%SZ`, overridable) once per invocation and pass
   them as `--build-arg` to every web image build.
3. **Each app's own `next.config.ts`** imports its own `package.json` and
   sets:
   ```ts
   env: {
     NEXT_PUBLIC_APP_VERSION: pkg.version,
     NEXT_PUBLIC_GIT_SHA: up("GIT_SHA", "dev"),
     NEXT_PUBLIC_BUILD_DATE: up("BUILD_DATE", ""),
   }
   ```
   Next.js performs this substitution at **build time** — nothing about the
   footer requires a runtime env var on the deployed Container App. Running
   `next dev` locally falls back to `NEXT_PUBLIC_GIT_SHA="dev"` and an
   empty build date.
4. **`packages/design-system/src/shell/VersionFooter.tsx`** is
   **presentation-only**: it takes `{ appName, version, gitSha,
   releaseDate?, tone? }` as **props** and reads no `process.env` itself,
   owns no global version state. Each app's own shell file resolves its own
   `NEXT_PUBLIC_*` values (and, once wired, its own runtime release date)
   and passes them explicitly:
   ```tsx
   <VersionFooter
     appName="DijiBirthday"
     version={process.env.NEXT_PUBLIC_APP_VERSION ?? "0.0.0"}
     gitSha={process.env.NEXT_PUBLIC_GIT_SHA ?? "dev"}
     releaseDate={releaseMeta?.release_date}
   />
   ```
   This is what makes "every app owns its own version" independently
   auditable by reading each app's own shell file — not a claim resting on
   a comment inside a shared component that reads environment variables
   internally (an earlier design did exactly that, and was corrected: a
   shared component that reads its own environment is not verifiably
   per-app just because the underlying build happens to produce different
   values per app).

`VersionFooter` takes a `tone` prop (`"dark"` default, sidebar's dark
gradient; `"light"` for the two header-shell apps — Supplier Portal,
TalentFlow Client Portal). The TalentFlow Client Portal keeps its existing
client-facing message ("A read-only view of your engagement, provided by
Dijital Team.") as the primary footer line, with its own `VersionFooter`
(`tone="light"`) rendered as a second, visually subtler line beneath it —
same architecture and metadata as every other app, just styled to not
compete with the existing client-facing copy. There is no product/security
reason to withhold a version number or commit SHA from an external
audience, so no app is exempt from this.

## Versioning rules for future changes

**The bump rule is release-target-aware, not diff-based**: *if an
application is selected for release AND its artifact differs from its
previously released artifact, its semantic version must advance. If an
application is NOT selected for release: don't deploy a new image for it,
don't change its version, don't change its release date* — full stop,
regardless of whether its source happens to be technically different due
to a shared dependency. **A repository/monorepo commit is not the same
thing as an application release, and a shared-package change is not an
automatic release of every consumer** — this is the one thing earlier
drafts of this policy got wrong and it's the whole point of this
correction.

- **Patch and minor increments** (`1.0.1 → 1.0.2`, `1.0.1 → 1.1.0`) are
  routine maintenance for a release target — the agent may make these
  without asking first.
- **Major version increments** (`1.x.x → 2.0.0`, `2.x.x → 3.0.0`, …)
  **require explicit user approval before being made.** Never bump a major
  version as a side effect of an unrelated change, and never infer
  approval from a request that doesn't explicitly authorize one.
- Each app's version is independent — bumping `birthday-web` says nothing
  about any other app's version.
- A shared `packages/*` workspace-package change (resolved transitively —
  a change two dependency levels deep still counts) means every dependent
  app's **image would differ if rebuilt** — that is **advisory
  information only**, never a requirement to bump/rebuild/redeploy an app
  that isn't actually being released this cycle. An app not selected for
  release keeps its current image, version, and release date untouched,
  even if its source would technically compile differently.
- The **initial `1.0.0` baseline** (September 2026) was a deliberate,
  explicitly user-approved exception to the major-bump-needs-approval rule
  (every app started from the untouched `0.1.0` scaffold default, never a
  deliberately chosen version) — that reasoning does not carry forward.

### Worked example: round 3 (Birthday-only)

`birthday-web` is the **only** release target this round (Upcoming
Birthdays responsive layout, Lead Time Class deep-link, the 3-line footer
+ per-app `RELEASE_DATE` mechanism) — **`1.0.1 → 1.0.2`**. The shared
`VersionFooter`/`PageHeader` source in `packages/design-system` also
changed, and the other 5 apps' shell files needed a small mechanical prop
update to stay compilable against the new `VersionFooter` shape — but
**none of the other 5 apps are release targets this round**: their
`package.json` versions, deployed images, and release dates are all left
exactly as they were. They pick up the 3-line footer format on their own
next release, whenever that is — not automatically now. (Compare with
round 2's mistake, corrected here: round 2 bumped all 6 apps together for
a purely presentational `VersionFooter` change, conflating "the shared
source changed" with "every consumer is being released.")

### Worked example: round 4 (full-application responsive hardening, Birthday-only)

Same policy applied again, this time for a full-app responsive-hardening
pass — `birthday-web` **`1.0.2 → 1.0.3`**. This round touched two
`packages/design-system` files (`Modal.tsx` — a genuine P0 fix, no more
unbounded-height panel that could push its footer buttons off-screen on a
short viewport; `MetricCard.tsx` — an additive truncation guard) as well as
Cake Orders, Suppliers, and Supplier Detail inside `birthday-web` itself.
Both shared-file changes were confirmed backward-compatible for their
other consumers (`talent-web`, `admin-web`, `birthday-supplier-web`,
`talentflow-portal-web` all reference `Modal`/`MetricCard`) by rebuilding
`admin-web` and `talent-web` as a sanity check before release — both build
clean. As with round 3, none of those other apps are release targets:
their versions, images, and release dates are untouched this round.

## Continuous enforcement: `npm run versions:check`

Documentation alone relies on a future session remembering the bump rule.
`scripts/check-app-versions.js`, run via:

```
npm run versions:check -- --apps <name>[,<name>...] [--base <ref>] [--committed]
```

**reports**, never auto-bumps, and never decides which apps to release —
that's an explicit, required input, not something the tool infers:

- **`--apps` is required.** Release-target selection must be a conscious,
  explicit choice every run — omitting it is a usage error, never an
  implicit "check every app in the workspace" default.
- **Default mode compares `<base>` (default `HEAD~1`) against the current
  working tree** — committed history since `<base>`, plus staged,
  unstaged, and untracked changes — because this is meant to run **before**
  a release commit exists. `--committed` restricts detection to
  `<base>..HEAD` only, for a CI context that only cares about committed
  history.
- **Release targets** (named via `--apps`): the app's version at `<base>`
  vs. the current working tree must differ, or it's a hard failure
  (`ERROR: version bump required`); a major-digit jump is flagged as
  needing explicit approval. **This is the only section that can fail the
  check.**
- **Affected by shared source but not selected for this release**: every
  other app whose `apps/<name>/` directory *or* a `packages/*` dependency
  it uses (resolved transitively) differs, but isn't named in `--apps` —
  reported as pure information. **Never gates the check, never implies
  those apps should be rebuilt or deployed.**
- The tool makes **no** patch-vs-minor decision itself — that stays an
  agent/contributor judgment call per the rules above.

Example output (this release):

```
Release targets:
  birthday-web               1.0.1 -> 1.0.2   OK

Affected by shared source but not selected for this release (informational only — NOT rebuilt/deployed):
  shell-web                  — app source
  admin-web                  — app source
  talent-web                 — app source
  talentflow-portal-web      — app source
  birthday-supplier-web      — app source

Untouched:
  (none)
```

Run this as a step in the release checklist (before finalizing a release
commit / before `deploy/deploy.sh`) — it is not wired into a blocking
pre-commit hook, since it's a release gate, not a per-commit interrupt.
Unit tests for its decision logic live in
`scripts/check-app-versions.test.js` (`npm run test:versions-check`); the
git-integration behavior itself is verified by actually running the tool
against real repository changes, which is the stronger proof for that part.

## Responsive/layout changes: the viewport-matrix requirement

Any significant responsive or layout change to shared shell components
(`AppShell`/`Sidebar`/`TopNav` in `packages/design-system`) or to a
page-level layout must be verified against the full viewport matrix — not
just a desktop screenshot — before it's considered done:

```
1920, 1440, 1280, 1180, 1024, 900, 768, 430, 390
```

At minimum, assert `document.documentElement.scrollWidth <=
window.innerWidth` at every width for the **whole rendered page**, not a
cropped element — a shared shell component overflowing is a shell bug and
must be fixed in the shell, never worked around inside one consuming app's
page. Puppeteer with a locally cached Chromium build is already available
in this repo's `node_modules` (no new dependency) for real headless-browser
verification; prefer it over reasoning about pixel budgets alone.

### `scripts/verify-birthday-responsive.js` — the committed, whole-app audit tool

Round 4 (the full DijiBirthday responsive-hardening pass) built one
reusable, **committed** Puppeteer script that drives every `birthday-web`
route through the full viewport matrix above in one run, rather than a
one-off scratchpad script per page. Run it via:

```
npm run birthday:responsive-check
```

It requires a live local stack — `platform-api` (port 8000), `birthday-api`
(port 8003, started with `INTEGRATIONS_MODE=mock` so employee data actually
loads instead of trying real BambooHR), and `birthday-web`
(`npm run dev` from `apps/birthday-web`, port 3003) — plus a dev bearer
token exported as `DEV_TOKEN`:

```bash
curl -s -X POST http://localhost:8000/api/auth/dev-login \
  -H "Content-Type: application/json" -d '{"persona_key":"super-admin"}'
# copy the access_token from the response, then:
DEV_TOKEN=<token> npm run birthday:responsive-check
DEV_TOKEN=<token> npm run birthday:responsive-check -- --screenshots
```

It self-seeds deterministic `/orders/<id>` and `/suppliers/<id>` route IDs
by reading whatever already exists in the local `birthday-api` database
(create at least one order — e.g. via a detection run — and one supplier
first if the database is empty). It asserts the whole-page overflow
invariant above on every route, runs a diagnostic pass that reports which
specific visible element is causing an overflow when one is found (skipping
elements that are hidden, zero-size, or intentionally inside their own
local `overflow-x-auto` container), and separately drives the tallest
modal (Add/Edit Supplier User) through real Chromium at short/landscape
mobile dimensions to prove the `Modal.tsx` height-cap/scroll fix actually
works — a jsdom unit test cannot prove real scroll/reachability behavior,
only the class/DOM contract that makes it possible.

Not wired into CI (it needs a live local stack CI doesn't currently
provision for `birthday-web`). Output under `responsive-audit/` (JSON
results, and screenshots when `--screenshots` is passed) is a regenerated
run artifact, gitignored — never committed.

## Follow-up work (not built yet — tracked here on purpose)

- **`RELEASE_DATE` for the other 5 apps.** Only `birthday-web` has the
  `/api/meta` force-dynamic Route Handler + shell wiring. The pattern is
  documented above; each other app adopts it on its own future release.
- **`main.bicep` `RELEASE_DATE` persistence.** Deliberately **not**
  touched this round. A `releaseDates object = {}` parameter with a
  default-empty map is only safe if every future `main.bicep` deployment
  reliably repopulates the full map first — shipping the parameter without
  that wrapper logic in the same change would be a half-built mechanism
  that silently erases an app's `RELEASE_DATE` the first time someone runs
  `main.bicep` for an unrelated reason (Container Apps `env` arrays are
  fully replaced, not merged, by a bicep deployment). **Do not add the
  bicep parameter without the wrapper logic in the same change.** When this
  is eventually built: `main.bicep` takes a `releaseDates` object keyed by
  service name (never one global value), and the deployment wrapper
  (`deploy/deploy.sh` or equivalent) is responsible for reading every
  currently-deployed service's live `RELEASE_DATE`, carrying them forward
  unchanged, and overwriting only the entry for the app(s) actually being
  released that run, before ever invoking `main.bicep`. Until this exists,
  **do not run a full multi-service `main.bicep` deployment against an
  environment that has any app-specific `RELEASE_DATE` set via
  `az containerapp update`** without first manually capturing and
  understanding what would be lost.

## Where this is enforced / referenced

- `deploy/Dockerfile.web` — build-arg plumbing (version/SHA — build-time
  only; `RELEASE_DATE` is deliberately NOT a build arg, see above).
- `deploy/build-images.sh`, `deploy/build-push.sh` — compute + pass
  `GIT_SHA`/`BUILD_DATE` for every web image build.
- Each app's `next.config.ts` — reads its own `package.json` version.
- `apps/birthday-web/src/app/api/meta/route.ts` — the force-dynamic
  runtime `RELEASE_DATE` endpoint (birthday-web only, so far).
- `packages/design-system/src/shell/VersionFooter.tsx` — the shared,
  presentation-only, prop-driven rendering component (3-line format).
- Each app's shell component (`birthday-shell.tsx`, `talent-shell.tsx`,
  `admin-shell.tsx`, `shell-web/src/app/page.tsx`,
  `birthday-supplier-web/src/app/app-shell.tsx`,
  `talentflow-portal-web/src/app/app-shell.tsx`) — resolves its own
  metadata and passes it to `VersionFooter` as props.
- `scripts/check-app-versions.js` + `npm run versions:check -- --apps
  <targets>` — continuous, release-target-aware enforcement of the bump
  rule.
- Root `CLAUDE.md`'s "PER-APPLICATION VERSIONING CONTRACT" — points here
  as the authoritative versioning convention.
