# DijiOne — Per-application versioning and footer build metadata

> Authoritative. Added when the footer's version/build display was
> implemented; corrected twice after review found the bump policy and the
> shared-component architecture still weren't right. This document is the
> source of truth for how each application's version is defined, how it
> reaches the UI, and the rules for who may change a major version number
> and when an app's version must move at all.

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
apps/birthday-web/package.json             "version": "1.0.1"
apps/birthday-supplier-web/package.json    "version": "1.0.1"
```

(`apps/*-api` backend services are not currently in scope for this
mechanism — this convention covers the six Next.js frontends, which is
where the footer lives. If a backend service ever needs the same treatment,
extend this same pattern rather than inventing a second one.)

## How the value reaches the UI

Three pieces of information are shown per app, in the existing footer area
(the bottom of that app's sidebar, or — for the two header-shell apps,
Supplier Portal and the TalentFlow Client Portal — a footer bar at the
bottom of the page):

| Value | Source | Baked in when |
|---|---|---|
| App version | That app's own `package.json` `"version"` | Every build, read directly by `next.config.ts` |
| Git commit SHA | The `GIT_SHA` Docker build arg | Container image build (`az acr build` / `docker build`) |
| **Build** date | The `BUILD_DATE` Docker build arg | Container image build |

### "Built" vs. a release date — these are not the same thing

`BUILD_DATE` identifies when the **artifact** (the container image) was
built — it is deliberately **not** called or labeled a release/deployment
date, because those are different concepts: an image can be built once and
later promoted/deployed unchanged to a different environment at a later
time, and conflating the two would misrepresent when something was
actually released. The rendered label is always **"Built {date}"**, never
a bare date and never "Release date":

```
DijiBirthday · by Dijital Team
v1.0.1 · 394527a · Built 2026-09-14
```

If a true deployment/release timestamp is ever needed, it is a **separate**
`RELEASE_DATE` value, injected by the deployment pipeline (not the image
build) — not implemented as of this writing; this is a deliberate, named
gap, not something silently folded into `BUILD_DATE`.

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
   **presentation-only**: it takes `{ appName, version, gitSha, buildDate?,
   tone? }` as **props** and reads no `process.env` itself, owns no global
   version state. Each app's own shell file resolves its own
   `NEXT_PUBLIC_*` values and passes them explicitly:
   ```tsx
   <VersionFooter
     appName="DijiBirthday"
     version={process.env.NEXT_PUBLIC_APP_VERSION ?? "0.0.0"}
     gitSha={process.env.NEXT_PUBLIC_GIT_SHA ?? "dev"}
     buildDate={process.env.NEXT_PUBLIC_BUILD_DATE}
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

**The bump rule is artifact-based, not visibility-based**: if an app's own
source/config changes and that app is rebuilt/released, its version
increments — full stop, regardless of whether an end user would notice the
difference. A pure internal refactor that changes a call site still counts,
because the released artifact is genuinely different from the last one.
The only apps that legitimately keep their prior version are ones with
**zero** changes in a given release.

- **Patch and minor increments** (`1.0.1 → 1.0.2`, `1.0.1 → 1.1.0`) are
  routine maintenance — the agent may make these as part of normal
  development without asking first.
- **Major version increments** (`1.x.x → 2.0.0`, `2.x.x → 3.0.0`, …)
  **require explicit user approval before being made.** Never bump a major
  version as a side effect of an unrelated change, and never infer
  approval from a request that doesn't explicitly authorize one.
- Each app's version is independent — bumping `birthday-web` says nothing
  about any other app's version, and every app happening to bump in the
  same release (see the worked example below) is a coincidence of that
  release's scope, not a shared version.
- A shared `packages/*` workspace-package change counts as changing every
  app that depends on it (**transitively** — a change two dependency levels
  deep still counts, not only direct dependencies), because those apps are
  genuinely rebuilt with different content even though their own `apps/`
  directory has no diff.
- The **initial `1.0.0` baseline** (September 2026) was a deliberate,
  explicitly user-approved exception to the major-bump-needs-approval rule:
  every app started from the untouched `0.1.0` scaffold default, never a
  deliberately chosen version, so establishing `1.0.0` was initializing
  versioning, not a major bump on an established product line. That
  reasoning does not carry forward.

### Worked example: this release

All 6 apps were genuinely touched by the release that introduced the
prop-driven `VersionFooter` (every app's shell file needed its call site
updated to the new prop shape) plus `birthday-web`'s own additional
`OrderDetail.tsx` responsive fix — so **all 6 apps bump `1.0.0 → 1.0.1`**,
including `talentflow-portal-web` (its footer gained a `VersionFooter` line
it didn't have before). This is not "bump everything by default" — the
next release that only touches `birthday-web` will only bump
`birthday-web`; `npm run versions:check` (below) is what catches the case
where a release should have bumped an app and didn't.

## Continuous enforcement: `npm run versions:check`

Documentation alone relies on a future session remembering the bump rule.
`scripts/check-app-versions.js` (run via `npm run versions:check [-- --base
<ref>] [-- --committed]`) **reports**, never auto-bumps — it detects the
"changed a released artifact but forgot to bump its version" case:

- **Default mode compares `<base>` (default `HEAD~1`) against the current
  working tree** — committed history since `<base>`, plus staged,
  unstaged, and untracked changes — because this is meant to run **before**
  a release commit exists, answering "what am I about to release?", not
  only "what did I already commit?" `--committed` restricts detection to
  `<base>..HEAD` only, for a CI context that only cares about committed
  history.
- An app counts as changed if any file under `apps/<name>/` differs, or any
  file in a `packages/*` workspace it depends on (resolved transitively)
  differs.
- The app's *current* version is always read from the filesystem
  `package.json` (so a working-tree edit is seen); its *base* version comes
  from `git show <base>:apps/<name>/package.json`.
- A changed app whose version **didn't move** is reported as
  `ERROR: version bump required` and the tool exits non-zero.
- A changed app whose version moved by a **major** digit is reported as
  `MAJOR VERSION CHANGE — USER APPROVAL REQUIRED` and also exits non-zero
  — not because a major bump is wrong, but because it must never pass
  silently as routine; a human confirms it was the explicitly-approved one.
- The tool makes **no** patch-vs-minor decision itself — that stays an
  agent/contributor judgment call per the rules above.

Example output:

```
Changed application artifacts:
  birthday-web              1.0.0 -> 1.0.1   OK
  talent-web                1.0.0 -> 1.0.1   OK
  admin-web                 1.0.0 -> 1.0.0   ERROR: version bump required

Untouched:
  talentflow-portal-web     1.0.1 (unchanged)
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

## Where this is enforced / referenced

- `deploy/Dockerfile.web` — build-arg plumbing.
- `deploy/build-images.sh`, `deploy/build-push.sh` — compute + pass
  `GIT_SHA`/`BUILD_DATE` for every web image build.
- Each app's `next.config.ts` — reads its own `package.json` version.
- `packages/design-system/src/shell/VersionFooter.tsx` — the shared,
  presentation-only, prop-driven rendering component.
- Each app's shell component (`birthday-shell.tsx`, `talent-shell.tsx`,
  `admin-shell.tsx`, `shell-web/src/app/page.tsx`,
  `admin-shell.tsx`, `birthday-supplier-web/src/app/app-shell.tsx`,
  `talentflow-portal-web/src/app/app-shell.tsx`) — resolves its own
  metadata and passes it to `VersionFooter` as props.
- `scripts/check-app-versions.js` + `npm run versions:check` — continuous
  enforcement of the bump rule.
- Root `CLAUDE.md`'s "PER-APPLICATION VERSIONING CONTRACT" — points here
  as the authoritative versioning convention.
