# DijiOne Design System

**Phase 2.5**: the components and tokens described below live in
`packages/design-system` now (a shared npm workspace package, not
`apps/web`) and are imported by all three frontend apps as
`@dijione/design-system`. The brand logo is copied into each frontend
app's own `public/brand/` (Next.js doesn't serve another package's
`public/` directory) — see `docs/platform/module-framework.md`
"Design-system inheritance".

## Brand research

The public Dijital Team site (`https://www.dijitalteam.com/`) was fetched
during this build. Its logo (`Dijital_Team_logo_XLGE.png`, saved locally at
`apps/shell-web/public/brand/dijital-team-logo.png` and duplicated into
`admin-web`/`talent-web`'s own `public/brand/`) uses a black wordmark with
four accent dots in amber, green, orange and red — confirming the warm
red/orange/amber direction already specified in CLAUDE.md §47-48, plus
green as an accent (used here only for semantic "success" states, per
§56, not as a UI accent color). The site's page chrome itself is mostly
black-on-white with no other brand colors exposed in static markup, so the
full palette below remains the CLAUDE.md-specified **derived** palette
(§48) rather than an extracted corporate style guide.

## Tokens

Defined once in `packages/design-system/src/globals.css` (copied into each
frontend app's own `src/app/globals.css` with a Tailwind v4 `@source`
directive — see `docs/platform/module-framework.md`) as CSS custom
properties and
mapped into Tailwind v4 via `@theme inline`, so every utility class
(`bg-dt-orange`, `text-dt-text-secondary`, …) resolves to the same source
of truth:

```css
/* Official Dijital Team brand system (docs/talent-flow/brand-baseline.md).
   The five sanctioned colours: black #000000, green #056839, red #BF1E2E,
   orange #F1592A, yellow #FCB040. The three formerly-invented red/orange
   token NAMES stay (shared Tailwind utility classes across every DijiOne
   app) but now each resolves to one of the two canonical hexes. */
--dt-red-deep: #bf1e2e;   /* = --dt-red */
--dt-red: #bf1e2e;
--dt-burnt-orange: #f1592a; /* = --dt-orange */
--dt-orange-deep: #f1592a;  /* = --dt-orange */
--dt-orange: #f1592a;
--dt-amber: #fcb040;
--dt-yellow-soft: #fcb040;  /* one yellow */

--dt-background: #f8f5f2;   /* warm off-white surfaces: brand extension,
--dt-surface: #ffffff;         not a sanctioned brand colour — kept as-is */
--dt-surface-warm: #fff8ef;
--dt-cream: #ffefd5;

--dt-text-primary: #111111; /* body text; #000000 is reserved for the logo */
--dt-text-secondary: #76584c;
--dt-border: #eadbd3;

--dt-success: #056839;      /* brand green = semantic success */
--dt-warning: #c78300;      /* readable dark amber for text; brand #FCB040
                              fails contrast as a text colour */
--dt-danger: #bf1e2e;       /* brand red = semantic danger */
--dt-info: #5b6472;         /* neutral, not a brand colour */

--font-sans: var(--font-be-vietnam-pro); /* talent-web + talentflow-portal-web */
```

Every component consumes the `--dt-*` variables, never a hardcoded hex —
so this one block is the single point of change.

> **Scope note.** The block above is the canonical source in
> `packages/design-system/src/globals.css`, which Tailwind v4 has no
> cross-package `@import` for, so each app keeps its own copy in
> `apps/<app>/src/app/globals.css`. The brand-alignment PR updated only
> **`talent-web`** and **`talentflow-portal-web`** (the DijiTalentFlow
> surfaces). `admin-web` / `birthday-web` / `birthday-supplier-web` /
> `shell-web` still hold the older derived palette in their own copies and
> are aligned in a later pass — they were explicitly out of scope for the
> Monitoring-First UX iteration.

### Official brand guideline — verified facts

Authoritative materials: `C:\Projects\Diji Projects\Dijital Team Brand
Guideline` (a READ‑ONLY reference exception — see root `CLAUDE.md` "Dijital
Team Branding Agent"). Full baseline: `docs/talent-flow/brand-baseline.md`.

- **Official colours (the only five):** Black `#000000`, Green `#056839`,
  Red `#BF1E2E`, Orange `#F1592A`, Yellow `#FCB040`. No sanctioned grey
  scale or gradient spec.
- **Supporting font:** **Be Vietnam Pro** (Google Fonts; weights 300 / 400
  / 600 / 700 in the apps). The logo/tagline custom font is never
  recreated — use the logo files.
- **Logo:** black lowercase `dijital team` wordmark, four‑dot `j` mark
  (yellow / orange / red / green). White/reversed version for dark or busy
  backgrounds; clear space = 2× dot width; min 120 px wide on screen.
  Rendered via the shared `<BrandLogo variant="dark"|"light" />` component
  from `@dijione/design-system`, backed by the official
  `Dijital_Team_logo_XLGE.png` copied into each app's own `public/brand/`.
  `variant="light"` applies a `brightness(0) invert(1)` filter for the
  sanctioned pure-white reversed treatment on dark backgrounds.

## Gradients

Used selectively (CLAUDE.md §49), never on every card:

- Sidebar background: `from-dt-red-deep via-dt-red to-dt-burnt-orange`
  (`packages/design-system/src/shell/Sidebar.tsx`)
- Primary buttons and the DijiOne "Ask DijiOne" panel:
  `from-dt-red to-dt-orange`
- Module icon tiles on Home: `from-dt-red to-dt-orange`

Cards themselves stay white/cream (`bg-dt-surface`, `bg-dt-surface-warm`).

## Semantic status colour rules

`components/ui/StatusBadge.tsx` maps every status/stage string used across
the app to one of five tones (CLAUDE.md §56):

| Tone    | Meaning                              | Examples |
|---------|----------------------------------------|----------|
| success | completed / on track / approved        | `APPROVED`, `FULFILLED`, `HIRED`, `COMPLETED`, `SYNCED` |
| warning | attention / waiting                    | `PENDING_REVIEW`, `CLARIFICATION_REQUIRED`, `ON_HOLD`, `OFFER` |
| danger  | error / rejected / destructive          | `REJECTED`, `CANCELLED`, `NO_SHOW`, `ERROR` |
| neutral | inactive / draft                        | `NOT_STARTED`, `WITHDRAWN`, `COMING_SOON` |
| brand   | navigation / current-stage emphasis     | `IN_PROGRESS`, `ACTIVE`, `SCHEDULED`, `CLIENT_REVIEW` |

Brand orange is intentionally **not** reused for every state — it is
reserved for navigation and "this is the current/active thing" emphasis so
it stays meaningful next to the semantic colours above.

## Typography

**Be Vietnam Pro** — the official Dijital Team supporting font (Google
Fonts), loaded via `next/font/google` in `app/layout.tsx` (weights 300 /
400 / 600 / 700) and exposed as `--font-be-vietnam-pro` → `--font-sans`.
Live in `talent-web` and `talentflow-portal-web`; the other apps still use
Geist Sans pending their own alignment pass (see the scope note under
Tokens). The type scale is unchanged — only the family. Geist Mono stays
as the monospace fallback.

## Components

Shared primitives live in `packages/design-system/src/ui/`, imported as
`@dijione/design-system`:

`Card`, `Button`, `StatusBadge`, `MetricCard` (optional `href` makes the
whole card a click-through link), `BrandLogo` (`variant="dark"|"light"`,
the official wordmark), `Table` (`Thead`/`Th`/`Tr`/`Td`),
`StageTimeline` / `CompactStageStrip` / `StageProgressBar`, `Modal`,
`FormField` (`Input`/`Textarea`/`Select`), `Avatar`, `PageHeader`,
`EmptyState` / `LoadingState` / `ErrorState`.

Shell-level composition lives in `packages/design-system/src/shell/`:
`AppShell`, `Sidebar`, `TopNav`, `NotificationsPanel`, `UserMenu`,
`DevPersonaSwitcher`, `AuthGate`.

Every DijiTalentFlow page composes these rather than re-implementing card/
table/badge styling locally (CLAUDE.md §54). The DijiOne Admin Center
(`apps/admin-web/src/app/*`, its own Next.js app since Phase 2.5) reuses
the identical set via the same `@dijione/design-system` import — no new
tokens, gradients, or primitive components were introduced for it, per the
requirement that Admin screens "feel like a natural part of DijiOne."

## Accessibility

- All interactive controls are real `<button>`/`<a>`/form elements (no
  click-handled `<div>`s).
- Focus states use `focus-visible:ring-2 focus-visible:ring-dt-orange`.
- Status is never conveyed by colour alone — every `StatusBadge` also
  carries a text label.
- Layouts use Tailwind's responsive prefixes (`sm:`/`lg:`) and tables sit
  inside `overflow-x-auto` containers, avoiding page-level horizontal
  scroll on small screens.
