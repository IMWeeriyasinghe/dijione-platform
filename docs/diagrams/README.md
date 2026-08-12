# Architecture & Workflow Diagrams

## Layout

```text
docs/diagrams/
├── source/     Mermaid (.mmd) files — the editable source of truth
└── rendered/   PNG exports, auto-generated from source/ — do not hand-edit
```

Every diagram embedded in [`docs/CURRENT_SYSTEM_WORKFLOW.md`](../CURRENT_SYSTEM_WORKFLOW.md) has a matching `.mmd` file here, named identically (e.g. `01-platform-architecture.mmd` → `01-platform-architecture.png`). `13-admin-center-flow.mmd` (Phase 2) is additionally referenced from [`docs/platform/admin-center.md`](../platform/admin-center.md).

## Regenerating the PNGs

From the repository root (`dijione-platform/`):

```bash
npm run diagrams
```

This runs [`scripts/generate-diagrams.js`](../../scripts/generate-diagrams.js), which renders every `.mmd` file in `source/` to a same-named `.png` in `rendered/` using `@mermaid-js/mermaid-cli` (`mmdc`). No VS Code Mermaid Preview or other manual step is required — this is the only command needed to keep the rendered diagrams in sync after editing a source file.

The script searches for an `mmdc` binary starting in this project's own `node_modules/.bin`, then walks up parent directories (covering a shared/parent-level install), then falls back to whatever `mmdc` resolves to on `PATH`. It exits non-zero and lists any diagram that failed to render.

## Editing a diagram

1. Edit the relevant file under `docs/diagrams/source/`.
2. Run `npm run diagrams`.
3. Commit both the changed `.mmd` file and its regenerated `.png` together.

Never edit a file under `rendered/` directly — it will be silently overwritten the next time the script runs.
