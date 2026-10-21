// Not `@testing-library/jest-dom/vitest`: that entry point imports `vitest`
// from inside `@testing-library/jest-dom` itself, which breaks in this
// monorepo — `vitest` is deliberately npm-nested under this app's own
// node_modules (its `picomatch@4` conflicts with eslint-config-next's
// `picomatch@2` elsewhere in the tree), so a bare `import "vitest"` from the
// hoisted jest-dom package can't resolve it. Importing `vitest`'s `expect`
// from here instead works because this file lives inside the same app
// subtree as the nested install. Same pattern as apps/talent-web.
import { cleanup } from "@testing-library/react";
import * as matchers from "@testing-library/jest-dom/matchers";
import { afterEach, expect } from "vitest";

expect.extend(matchers);

// `globals: false` in vitest.config.ts means RTL's own auto-cleanup
// registration (which looks for a global `afterEach`) never fires —
// without this, DOM from one test's render() leaks into the next.
afterEach(() => cleanup());
