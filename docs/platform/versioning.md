# DijiOne — Per-application versioning and footer build metadata

> Authoritative. Added when the footer's version/build display was
> implemented. This document is the source of truth for how each
> application's version is defined, how it reaches the UI, and the rule for
> who may change a major version number.

## The rule, in one sentence

**Every application in this monorepo owns its own version number.** There is
no shared, platform-wide DijiOne version — `shell-web` has its own,
`birthday-web` has its own, `birthday-supplier-web` has its own, and so on.
Showing the same version number in two different apps' footers is a defect,
not a feature.

## Where an app's version lives

Each app's version is the `"version"` field in **that app's own**
`package.json` — nowhere else. There is no central version registry and no
build-time override of this value; it is only ever edited directly in the
owning app's `package.json`.

```
apps/shell-web/package.json               "version": "1.0.0"
apps/admin-web/package.json                "version": "1.0.0"
apps/talent-web/package.json               "version": "1.0.0"
apps/talentflow-portal-web/package.json    "version": "1.0.0"
apps/birthday-web/package.json             "version": "1.0.0"
apps/birthday-supplier-web/package.json    "version": "1.0.0"
```

(`apps/*-api` backend services are not currently in scope for this
mechanism — this convention covers the six Next.js frontends, which is
where the footer lives. If a backend service ever needs the same treatment,
extend this same pattern rather than inventing a second one.)

## How the value reaches the UI

Three pieces of information are shown per app, all in the existing footer
area at the bottom of that app's sidebar (or, for the two apps that use a
header-based shell instead of a sidebar — Supplier Portal and the
TalentFlow Client Portal — a footer bar at the bottom of the page):

| Value | Source | Baked in when |
|---|---|---|
| App version | That app's own `package.json` `"version"` | Every build, read directly by `next.config.ts` |
| Git commit SHA | The `GIT_SHA` Docker build arg | Container image build (`az acr build` / `docker build`) |
| Build/release date | The `BUILD_DATE` Docker build arg | Container image build |

The mechanism, end to end:

1. **`deploy/Dockerfile.web`** declares `ARG GIT_SHA=unknown` and
   `ARG BUILD_DATE=unknown`, set as `ENV` before the `npm run build` step of
   the build stage (never carried into the run stage — multi-stage builds
   don't leak `ENV` across `FROM` boundaries, so nothing about this touches
   the running container's environment).
2. **`deploy/build-images.sh`** and **`deploy/build-push.sh`** compute
   `GIT_SHA` (`git rev-parse --short=12 HEAD`, overridable) and `BUILD_DATE`
   (`date -u +%Y-%m-%dT%H:%M:%SZ`, overridable) once per invocation and pass
   them as `--build-arg` to every web image build. A manual `az acr build`
   should do the same — see either script for the exact flags.
3. **Each app's own `next.config.ts`** imports its own `package.json` and
   sets:
   ```ts
   env: {
     NEXT_PUBLIC_APP_VERSION: pkg.version,
     NEXT_PUBLIC_GIT_SHA: up("GIT_SHA", "dev"),
     NEXT_PUBLIC_BUILD_DATE: up("BUILD_DATE", ""),
   }
   ```
   Next.js performs this substitution at **build time** — the deployed
   container never reads these from its runtime environment, so nothing
   about the footer requires a runtime env var to be set on the Container
   App itself. Running `next dev` locally (no build args set) falls back to
   `NEXT_PUBLIC_GIT_SHA="dev"` and an empty build date — never a crash,
   never a stale/misleading value.
4. **`packages/design-system/src/shell/VersionFooter.tsx`** is the one
   shared component every app's shell renders (`<VersionFooter
   appLabel="DijiBirthday" />`, etc.). It reads
   `process.env.NEXT_PUBLIC_APP_VERSION` / `NEXT_PUBLIC_GIT_SHA` /
   `NEXT_PUBLIC_BUILD_DATE` directly rather than taking them as props.
   This is deliberate, not an oversight: each consuming app transpiles this
   shared package into its **own** Next.js build
   (`transpilePackages`), so Next's build-time literal substitution
   produces a **different value per app** from the exact same component
   source — which is what actually enforces "no shared platform-wide
   version," rather than merely documenting it as a convention someone
   could forget to follow.

Rendered output looks like:

```
DijiBirthday · by Dijital Team
v1.0.0 · 8a11d3e971b4 · 2026-09-14
```

`VersionFooter` takes a `tone` prop (`"dark"` by default, matching the
sidebar's dark gradient background; `"light"` for the two header-shell apps
rendering on a white surface — Supplier Portal, TalentFlow Client Portal).
The TalentFlow Client Portal's own footer intentionally keeps its existing
external-client-facing message ("A read-only view of your engagement,
provided by Dijital Team.") without added build metadata — that surface is
reached directly by external clients via a magic link, and internal commit
SHAs have no value to that audience. If a future requirement changes that,
apply the same `VersionFooter` pattern used in the Supplier Portal.

## Versioning rules for future changes

- **Patch and minor increments** (`1.0.0 → 1.0.1`, `1.0.0 → 1.1.0`) are
  routine maintenance. The agent (or any contributor) may bump these as
  part of normal development — landing a bug fix bumps the patch digit,
  landing a new feature bumps the minor digit — without asking first.
- **Major version increments** (`1.x.x → 2.0.0`, `2.x.x → 3.0.0`, …)
  **require explicit user approval before being made.** Do not bump a
  major version number as a side effect of an unrelated change, and do not
  infer approval from a request that doesn't explicitly authorize a major
  bump. If a change feels "major" enough to warrant one, stop and ask
  rather than deciding unilaterally.
- Each app's version is independent — bumping `birthday-web` to `1.2.0`
  says nothing about `talent-web`'s version, and vice versa.
- The **initial `1.0.0` baseline** (September 2026) was a deliberate,
  explicitly user-approved exception to the rule above: every app started
  from the untouched `0.1.0` scaffold default from `create-next-app`, never
  a deliberately chosen version, so establishing `1.0.0` as each app's real
  starting point was treated as initializing versioning rather than as a
  major bump on an established product line. That reasoning does not carry
  forward — every `x.0.0` change from here on is a real major bump and
  needs approval under the rule above.

## Where this is enforced / referenced

- `deploy/Dockerfile.web` — build-arg plumbing.
- `deploy/build-images.sh`, `deploy/build-push.sh` — compute + pass
  `GIT_SHA`/`BUILD_DATE` for every web image build.
- Each app's `next.config.ts` — reads its own `package.json` version.
- `packages/design-system/src/shell/VersionFooter.tsx` — the shared
  rendering component.
- Each app's shell component (`birthday-shell.tsx`, `talent-shell.tsx`,
  `admin-shell.tsx`, `shell-web/src/app/page.tsx`,
  `birthday-supplier-web/src/app/app-shell.tsx`) — wires `VersionFooter`
  into that app's existing footer slot.
- Root `CLAUDE.md` — points here as the authoritative versioning
  convention (see its own reference near the design-system section).
