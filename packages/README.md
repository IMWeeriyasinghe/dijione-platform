# DijiOne Shared Packages

No physical `packages/ui`, `packages/auth`, `packages/config`,
`packages/types`, or `packages/api-client` split exists yet — see
[`../docs/decisions/0001-monorepo-layout.md`](../docs/decisions/0001-monorepo-layout.md).
Their equivalents today:

| Suggested package | Current location |
|---|---|
| `packages/ui` | `apps/web/src/components/ui/*` |
| `packages/auth` | `apps/web/src/lib/auth-context.tsx` + `apps/api/app/core/security.py` |
| `packages/config` | `apps/web/src/lib/constants.ts` + `apps/api/app/core/constants.py` (hand-kept in sync) |
| `packages/types` | `apps/web/src/lib/types.ts` (hand-kept in sync with `apps/api/app/schemas/*`) |
| `packages/api-client` | `apps/web/src/lib/api.ts` |

Worth revisiting once a second app (not just a second module) needs to
share this code — see the ADR for the threshold.
