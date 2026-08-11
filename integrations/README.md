# DijiOne Integrations

Provider adapter *code* lives inside `apps/api/app/integrations/{lever,hubspot}`
(FastAPI cannot import Python modules from outside its own app tree
without a package split that isn't justified at MVP scale — see
[`../docs/decisions/0001-monorepo-layout.md`](../docs/decisions/0001-monorepo-layout.md)).

This directory documents the integration contracts:

- [`../docs/integrations/lever.md`](../docs/integrations/lever.md)
- [`../docs/integrations/hubspot.md`](../docs/integrations/hubspot.md)

Both providers are mock-only in this build phase (no credentials supplied,
CLAUDE.md §58). `apps/api/app/integrations/factory.py` is the single seam
that switches between mock and live clients via `INTEGRATIONS_MODE`.
