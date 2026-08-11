# DijiOne Modules

This directory is intentionally not a code package. See
[`../docs/decisions/0001-monorepo-layout.md`](../docs/decisions/0001-monorepo-layout.md)
for why module code lives inside `apps/web` and `apps/api` (namespaced by
`module_key`) rather than here, and
[`../docs/platform/module-framework.md`](../docs/platform/module-framework.md)
for how to add a new module.

Current modules: `talent-flow` (DijiTalentFlow, active), `birthday`
(DijiBirthday, registry placeholder), `spark` (DijiSpark, registry
placeholder).
