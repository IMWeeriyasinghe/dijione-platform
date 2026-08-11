# DijiOne Design System

## Brand research

The public Dijital Team site (`https://www.dijitalteam.com/`) was fetched
during this build. Its logo (`Dijital_Team_logo_XLGE.png`, saved locally at
`apps/web/public/brand/dijital-team-logo.png`) uses a black wordmark with
four accent dots in amber, green, orange and red — confirming the warm
red/orange/amber direction already specified in CLAUDE.md §47-48, plus
green as an accent (used here only for semantic "success" states, per
§56, not as a UI accent color). The site's page chrome itself is mostly
black-on-white with no other brand colors exposed in static markup, so the
full palette below remains the CLAUDE.md-specified **derived** palette
(§48) rather than an extracted corporate style guide.

## Tokens

Defined once in `apps/web/src/app/globals.css` as CSS custom properties and
mapped into Tailwind v4 via `@theme inline`, so every utility class
(`bg-dt-orange`, `text-dt-text-secondary`, …) resolves to the same source
of truth:

```css
--dt-red-deep: #8f2417;
--dt-red: #aa2f1d;
--dt-burnt-orange: #c9431d;
--dt-orange-deep: #db4d18;
--dt-orange: #f26a1b;
--dt-amber: #f59e0b;
--dt-yellow-soft: #fbc34a;

--dt-background: #f8f5f2;
--dt-surface: #ffffff;
--dt-surface-warm: #fff8ef;
--dt-cream: #ffefd5;

--dt-text-primary: #24140f;
--dt-text-secondary: #76584c;
--dt-border: #eadbd3;

--dt-success: #138a4b;
--dt-warning: #c78300;
--dt-danger: #c62d26;
--dt-info: #5b6472;
```

If Dijital Team supplies an official brand guideline later, only this one
block needs to change — every component consumes the `--dt-*` variables,
never a hardcoded hex value.

## Gradients

Used selectively (CLAUDE.md §49), never on every card:

- Sidebar background: `from-dt-red-deep via-dt-red to-dt-burnt-orange`
  (`components/shell/Sidebar.tsx`)
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

Geist Sans (via `next/font/google`, already wired in `app/layout.tsx`) — a
modern, professional, open sans-serif used as the CLAUDE.md §53-compliant
fallback until an official Dijital Team web font can be confirmed and
licensed for the application.

## Components

Shared primitives live in `apps/web/src/components/ui/`:

`Card`, `Button`, `StatusBadge`, `MetricCard`, `Table` (`Thead`/`Th`/`Tr`/`Td`),
`StageTimeline` / `CompactStageStrip` / `StageProgressBar`, `Modal`,
`FormField` (`Input`/`Textarea`/`Select`), `Avatar`, `PageHeader`,
`EmptyState` / `LoadingState` / `ErrorState`.

Shell-level composition lives in `components/shell/`: `AppShell`, `Sidebar`,
`TopNav`, `NotificationsPanel`, `UserMenu`, `DevPersonaSwitcher`, `AuthGate`.

Every DijiTalentFlow page composes these rather than re-implementing card/
table/badge styling locally (CLAUDE.md §54).

## Accessibility

- All interactive controls are real `<button>`/`<a>`/form elements (no
  click-handled `<div>`s).
- Focus states use `focus-visible:ring-2 focus-visible:ring-dt-orange`.
- Status is never conveyed by colour alone — every `StatusBadge` also
  carries a text label.
- Layouts use Tailwind's responsive prefixes (`sm:`/`lg:`) and tables sit
  inside `overflow-x-auto` containers, avoiding page-level horizontal
  scroll on small screens.
