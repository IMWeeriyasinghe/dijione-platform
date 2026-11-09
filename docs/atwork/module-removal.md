# DijiAtWork — module removal

Removing DijiAtWork must leave the rest of DijiOne operational. The
`atwork-removal-api` and `atwork-removal-web` jobs in `module-boundaries.yml`
delete `apps/atwork-*` and then test, migrate and build every remaining service.
`scripts/check-module-independence.js` rejects references outside the module's
own apps and its registration points.

## Registration points (data or config only, inert when absent)

- `platform-api`: catalog, seed and registry migration `atw1reg0b2c3`.
- `shell-web`: rewrites and the `ModuleCard` summary path.
- `scripts/dev-all.js`, root workspaces, CI workflows and docs.

## Permanent removal

1. Disable the `atwork` registry row in the Admin Center. Never revert the migration.
2. Remove the deployed services: see `deployment.md`.

Removing the module leaves its catalog rows in place, unused.
