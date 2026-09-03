# DIJITAL TEAM BRAND BASELINE — DIJITALENTFLOW

Read-only brand discovery run for the Monitoring-First UX & Client Access
Refinement iteration. Compares the authoritative Dijital Team brand materials
against `packages/design-system`, `apps/talent-web`, and
`apps/talentflow-portal-web`. All colour / typography / logo values below are
verified from the authoritative folder, not inferred from the current app.

> **Status (post PR 11):** the design-system colour tokens and the
> `talent-web` / `talentflow-portal-web` copies are now aligned to the five
> official colours; `--font-sans` is Be Vietnam Pro in those two apps; the
> official `_XLGE.png` wordmark is in each app's `public/brand/` and rendered
> via the new shared `<BrandLogo>`; the external portal shell + access screen
> carry the logo and the `#F1592A` eyebrow. Items still open by design:
> `admin-web` / `birthday-web` / `birthday-supplier-web` / `shell-web`
> token+font alignment (out of scope this iteration); a true vector-exported
> white logo asset (the current `variant="light"` uses a CSS filter on the
> black wordmark — geometry-preserving and guideline-compliant, but a
> dedicated reversed export from the `.eps` is a later nicety); the FUTURE
> ENTRA/SSO assets in §K.

Authoritative source (READ-ONLY): `C:\Projects\Diji Projects\Dijital Team Brand Guideline`.

---

## A. Brand asset inventory

| Category | Asset | Source path (under the brand folder) | Type | Purpose | Light/Dark | Recommended app usage | Notes |
|---|---|---|---|---|---|---|---|
| Guideline | Brand Guidelines - Dijital Team | `Brand Guidelines - Dijital Team .pdf` | PDF, 15 MB | Full brand system | — | Reference only | Image-heavy; not page-rendered in this environment (no poppler). The 1-page style guide is the authoritative summary used here. |
| Guideline | Dijital Team Style Guidelines | `Dijital Team Style Guidelines.pdf` | PDF, 1 page | Logo / colour / font / clear-space / min-size quick reference | — | Reference only | **Authoritative summary.** Read in full. |
| Logo (vector) | Dijital Team logo | `Digital Team Logos/Logo/Dijital Team logo.eps`, `.pdf` | EPS / PDF | Master logo | both (recolourable) | Export source for PNG/SVG + the white/reversed version | Preferred origin for a clean repo asset. |
| Logo (raster) | Dijital_Team_logo_{SML,MED,LGE,XLGE} | `Digital Team Logos/Logo/*.png` `*.jpg` | PNG (transparent) / JPG | On-screen logo | light backgrounds only (black wordmark) | Replace the repo's current approximate copy with `_XLGE.png` | 4-dot "ji" mark: yellow, orange, red, green stacked. |
| Colour | 5-colour palette | Style Guidelines p.1 | — | Brand colours | — | See §B | Exactly five. |
| Type | Be Vietnam Pro (Light, Bold) | Style Guidelines p.1 | Google Font | Supporting font | — | `--font-sans` for `talent-web` + `talentflow-portal-web` | Logo/tagline custom font is never recreated. |
| Imagery | Teams background | `Dijital Team - Teams Background.jpg` | JPG | MS Teams meeting background | dark | Not app chrome | — |
| Imagery | Desktop wallpaper | `Finalized Desktop Wallpaper design.png` | PNG | Desktop wallpaper | — | Not app UI | — |
| Auth / SSO | MS 365 login favicon | `MS 365 login page design components/MS 365 Login Page - Favicon - 32X32 px 5KB.png` | PNG 32×32 | Entra sign-in favicon | — | FUTURE ENTRA branding | — |
| Auth / SSO | MS 365 square logo | `.../MS 365 login page - Square Logo - 240 x 240px...png` | PNG 240×240 | Entra sign-in square logo | — | FUTURE ENTRA branding | — |
| Auth / SSO | MS 365 wallpaper | `.../MS 365 login page - Wallpaper - 1920 x 1080px...jpg` | JPG 1920×1080 | Entra sign-in background | dark | FUTURE ENTRA branding | Warm sunset-over-mountains photo, white logo bottom-right. Establishes the login imagery mood. |
| Auth / SSO | MS 365 header/banner logo | `.../MS 365 login page- Header logo and banner logo - 280 x 60px...png` | PNG 280×60 | Entra sign-in header | reversed (white on orange) | FUTURE ENTRA branding | Orange gradient panel, white "dijital team" + tagline "achieve more offshore" + circle/triangle decorations. Confirms a **white/reversed logo exists**. |
| Template | PowerPoint templates | `35d962c8-...potx`, `DJT Template_v01.pptx` | POTX / PPTX | Deck templates | — | Visual-language reference only | Not imported. |
| (junk) | `__MACOSX/` | `Digital Team Logos/__MACOSX/` | — | macOS resource forks | — | Ignore | — |

---

## B. Official colour system (verified — the only sanctioned colours)

| Role | HEX | RGB | CMYK |
|---|---|---|---|
| **Black** | `#000000` | 0 / 0 / 0 | 0 / 0 / 0 / 100 |
| **Green** | `#056839` | 5 / 104 / 57 | 90 / 30 / 95 / 30 |
| **Red** | `#BF1E2E` | 191 / 30 / 45 | 15 / 100 / 90 / 10 |
| **Orange** | `#F1592A` | 241 / 89 / 42 | 0 / 80 / 95 / 0 |
| **Yellow** | `#FCB040` | 252 / 176 / 64 | 0 / 35 / 85 / 0 |

There is **no sanctioned neutral/grey palette, no gradient spec, and no
tint/shade scale** in the style guide. The warm off-white surfaces currently
used in DijiTalentFlow (`--dt-background #f8f5f2`, `--dt-surface-warm #fff8ef`,
`--dt-cream #ffefd5`, `--dt-border #eadbd3`) are consistent with the brand's
warmth and the approved DijiTalentFlow visual direction (CLAUDE.md §50) and may
remain; they are extensions, not brand colours.

---

## C. Typography guidance

- **Supporting font: Be Vietnam Pro** (Google Fonts). The style guide shows
  **Light** and **Bold**; use **300 / 400 / 600 / 700** in the apps.
- The logo and tagline use a **custom font** supplied only via the logo files —
  **never recreate it**; use the logo image.
- Keep the existing DijiOne type scale (page title / section / card / body /
  metadata / caption / table header) — only the family changes.
- A monospace fallback (Geist Mono or system mono) may stay for code-ish text.

---

## D. Logo guidance

- **Primary logo:** black lowercase `dijital team` wordmark. The `j` ascender is
  replaced by a vertical stack of four dots — yellow, orange, red, green.
- **Tagline lockup:** wordmark + `achieve great outcomes with a great team`
  (style guide). A second tagline `achieve more offshore` appears on the MS-365
  login header. Use the plain wordmark in app chrome; taglines only where a
  marketing lockup is appropriate.
- **Backgrounds:** a **white/reversed** text version is used on dark backgrounds.
  On busy imagery, place the logo on a **white panel** sized to the clear-space
  area.
- **Clear space:** minimum equal to **2× the width of the logo dots** on all sides.
- **Minimum size:** **120 px wide** on screen (without tagline); 30 mm in print.
- **Prohibited:** recreating the logo/tagline font; recolouring the wordmark
  (other than the sanctioned white version); stretching / distorting; placing on
  a busy background without a white panel.

---

## E. Authentication / login assets

The `MS 365 login page design components/` set (favicon 32×32, square logo
240×240, wallpaper 1920×1080, header/banner 280×60) is for **Microsoft Entra /
M365 tenant company-branding configuration**.

- **LOCAL APPLICATION UI:** nothing here is for the local app screens. The
  Client Talent Review Workspace access/redeem screen should use the standard
  primary logo on a white card; a very-low-opacity warm background *inspired by*
  the login wallpaper mood is optional but must not reduce readability.
- **FUTURE ENTRA / CLOUD BRANDING:** the four MS-365 assets, applied when SSO is
  stood up, via the Entra portal. Not part of any local-UI PR. Catalogue only.

---

## F. Current design-system alignment (`packages/design-system/src/globals.css`)

| Token / item | Current | Verdict | Target |
|---|---|---|---|
| `--dt-red-deep` `#8f2417` | invented | **UPDATE (retire)** | remove; map uses to `--dt-red` |
| `--dt-red` `#aa2f1d` | invented | **UPDATE** | `#BF1E2E` |
| `--dt-burnt-orange` `#c9431d` | invented | **UPDATE (retire)** | remove; map uses to `--dt-orange` |
| `--dt-orange-deep` `#db4d18` | invented | **UPDATE (retire)** | remove; map uses to `--dt-orange` |
| `--dt-orange` `#f26a1b` | close, not exact | **UPDATE** | `#F1592A` |
| `--dt-amber` `#f59e0b` | invented | **UPDATE** | `#FCB040` |
| `--dt-yellow-soft` `#fbc34a` | invented | **UPDATE** | `#FCB040` (single yellow) |
| `--dt-success` `#138a4b` | invented | **UPDATE** | `#056839` (brand green = semantic success) |
| `--dt-danger` `#c62d26` | invented | **UPDATE** | `#BF1E2E` |
| `--dt-warning` `#c78300` | invented | **KEEP** | keep a readable dark amber for *text*; `#FCB040` fails contrast as a text colour |
| `--dt-info` `#5b6472` | neutral | **KEEP** | not a brand colour; acceptable neutral |
| surfaces / border / text-secondary | warm off-whites | **KEEP** | consistent with brand warmth; extensions, not brand colours |
| `--dt-text-primary` `#24140f` | warm near-black | **UPDATE** | `#111111` for body (pure `#000` is harsh at small sizes); `#000000` only for the logo |
| `--font-sans` = `var(--font-geist-sans)` | Geist | **UPDATE** | Be Vietnam Pro |
| gradient (sidebar) | red→orange, invented shades | **KEEP concept, UPDATE hex** | `#BF1E2E → #F1592A`; one gradient only (sidebar / module header), never on cards |
| `Card` / `Button` / `Input` / `Select` / `FormField` / `Table` / `PageHeader` / `EmptyState` | fine | **KEEP** | verify `Button` primary resolves to `#F1592A` after the swap |
| `StatusBadge` tone hexes | derived from tokens | **UPDATE (recheck)** | recompute Active/Expired/Revoked + canonical-stage tones after the token swap; contrast-check |
| `MetricCard` | static | **ADD** | accept an optional `href`/`onClick` for dashboard click-through (plan §D) — benefits every app |
| Brand logo component | none | **ADD** | `<BrandLogo variant="dark"|"light" />` in the design system wrapping one asset source |

**Net:** one canonical value per brand colour; retire the three invented
red/orange shades; align semantic success/danger to the official green/red;
switch the sans font. Contrast-check every heading/badge/label after the swap.

---

## G. Internal DijiTalentFlow alignment (`apps/talent-web`)

| Screen / area | Assessment | Gap |
|---|---|---|
| Colour usage across all screens | **PARTIALLY ALIGNED** | Inherits the invented red/orange family; fixed centrally by the token swap. |
| Font | **NOT ALIGNED** | Geist, not Be Vietnam Pro (`src/app/layout.tsx`). |
| Shell header (`talent-shell.tsx`) | **PARTIALLY ALIGNED** | Text "DijiTalentFlow" lockup; should use the official logo + a "DijiTalentFlow" product label. Uses `text-white/60` footer — fine. |
| Logo asset | **PARTIALLY ALIGNED** | `public/brand/dijital-team-logo.png` is an approximate copy; replace with `_XLGE.png`; add a white/reversed version for the gradient sidebar. |
| Operations Dashboard, All Requests, Candidate Pool, Request Detail, Applications, Interview Manager, Recruitment Postings | **ALIGNED (structure)** | Structurally fine; inherit token/font fixes automatically. No layout rework for branding. |
| Client Access Links generate form | **NOT ALIGNED (also a functional change)** | Cramped padding / spacing / hierarchy — addressed in plan §H. |
| `StatusBadge`, `MetricCard`, `Card` usage | **ALIGNED** | Semantic model kept; only underlying hexes change. |

---

## H. External Client Talent Review Workspace alignment (`apps/talentflow-portal-web`)

| Screen / area | Assessment | Gap |
|---|---|---|
| Font (`src/app/layout.tsx`) | **NOT ALIGNED** | Geist; must be Be Vietnam Pro. |
| Logo | **NOT ALIGNED** | No `public/brand/` folder; no logo shown anywhere. Add the primary logo to the header and the access/redeem card. |
| Eyebrow colour (`app-shell.tsx`) | **NOT ALIGNED** | `text-dt-burnt-orange` (retired shade) → `text-dt-orange` (`#F1592A`). |
| Access / redeem screen (`access/page.tsx`, `app-shell.tsx` NoSession) | **PARTIALLY ALIGNED** | Plain card; should carry the logo on a white card, optional low-opacity warm background, "Client Talent Review Workspace — Provided by Dijital Team". |
| Dashboard / Requests / Request Detail | **PARTIALLY ALIGNED** | Hand-rolled empty states and headers; should use design-system `EmptyState` / `PageHeader` / `Card`. Structure is otherwise fine. |
| Colour usage | **PARTIALLY ALIGNED** | Inherits the token family; fixed by the swap. |

**Highest care:** this is the client-facing surface — logo, font, and the
access screen are the priority.

---

## I. Highest-priority brand corrections (ordered)

1. **`talentflow-portal-web`** — Be Vietnam Pro, official logo asset (header + access card), `text-dt-orange` eyebrow, design-system `EmptyState`/`PageHeader`. External, client-facing.
2. **Design-system colour tokens** — the 5 official hex values; retire `--dt-red-deep` / `--dt-burnt-orange` / `--dt-orange-deep`; align `--dt-success` / `--dt-danger`. Fixing this corrects most internal screens at once.
3. **`talent-web` shell header** — official logo instead of the text lockup; Be Vietnam Pro.
4. **Client Access Links generate form** — spacing/hierarchy (also plan §H).
5. **Logo assets** — replace the approximate `dijital-team-logo.png` with `_XLGE.png`; add a white/reversed version; add one to `talentflow-portal-web`.

---

## J. Assets recommended for later repo import

| Source asset | Destination | Where used |
|---|---|---|
| `Digital Team Logos/Logo/Dijital_Team_logo_XLGE.png` | `packages/design-system/src/assets/brand/dijital-team-logo.png` (and/or per-app `public/brand/`) | `<BrandLogo variant="dark">` — light backgrounds |
| White/reversed wordmark exported from `Digital Team Logos/Logo/Dijital Team logo.eps` | `.../brand/dijital-team-logo-white.png` | `<BrandLogo variant="light">` — gradient sidebar, dark headers |
| (optional) "ji" dot-mark crop exported from the vector | `.../brand/dijital-team-mark.png` | favicon / compact contexts |

Do not depend on the Windows brand folder at runtime. Do not recolour/crop the
official wordmark beyond the sanctioned white version. Copy only what is listed.

---

## K. Future Entra / SSO branding items (catalogue only — NOT this iteration)

`MS 365 login page design components/` → favicon 32×32, square logo 240×240,
wallpaper 1920×1080 (warm sunset, white logo), header/banner 280×60 (orange
panel, white logo + "achieve more offshore"). Apply via the **Microsoft Entra
tenant company-branding** configuration when SSO is stood up. No local-UI PR
touches these.

---

## L. What should remain unchanged

- Warm off-white surface treatment (`--dt-background`, `--dt-surface`,
  `--dt-surface-warm`, `--dt-cream`, `--dt-border`) — consistent with brand
  warmth and CLAUDE.md §50.
- The red→orange sidebar gradient **concept** (re-point at `#BF1E2E → #F1592A`).
- `StatusBadge` semantic model (success / warning / danger / neutral / brand) —
  only the underlying hexes change.
- Layout / structure of **All Requests**, **Candidate Pool**, **Request Detail**,
  **Operations Dashboard**, **Applications**, **Interview Manager**,
  **Recruitment Postings** — they inherit the token/font fixes; do not re-lay-out
  them for branding.
- The design-system component APIs (`Card`, `Button`, `Input`, `Select`,
  `Table`, `PageHeader`, `EmptyState`) — token-level changes only, plus the one
  additive `MetricCard` `href` prop and the new `<BrandLogo>`.
- `admin-web` / `birthday-web` / `birthday-supplier-web` — out of scope this
  iteration.

---

## Reconciliation with plan §P

Plan §P and this baseline agree on: the 5-colour palette, Be Vietnam Pro,
retiring the invented red/orange shades, the official logo swap + white variant,
`MetricCard` href + `<BrandLogo>` additions, and "structure stays, tokens
change". Minor corrections folded in here:

- **Dot order** on the "ji" mark is yellow / orange / red / green (top→bottom),
  not "orange/red/green/yellow" — cosmetic, affects nothing but a caption.
- **Two taglines** exist (`achieve great outcomes with a great team`,
  `achieve more offshore`) — use the plain wordmark in app chrome, neither
  tagline in operational UI.
- The **login wallpaper mood** (warm sunset photography, white logo) informs the
  external access screen's optional background but must stay very low opacity;
  do not import that photo.
- The big brand PDF could not be page-rendered in this environment; if deeper
  imagery/grid/do-and-don't guidance is needed later, render it with poppler and
  extend this baseline. The 1-page style guide is sufficient for the PR 11 scope.
