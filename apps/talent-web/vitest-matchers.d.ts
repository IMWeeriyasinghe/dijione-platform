// Augments Vitest's `expect` with jest-dom matcher types, without importing
// `@testing-library/jest-dom/vitest` (see vitest.setup.ts for why that
// subpath's own `import 'vitest'` can't resolve in this monorepo). This file
// lives inside apps/talent-web, so its `declare module "vitest"` correctly
// merges against the nested apps/talent-web/node_modules/vitest, unlike the
// same augmentation shipped inside the hoisted jest-dom package.
import "vitest";
import type matchersStandalone from "@testing-library/jest-dom/matchers";

/* eslint-disable @typescript-eslint/no-explicit-any, @typescript-eslint/no-empty-object-type --
   Standard TS declaration-merging idiom (identical shape to jest-dom's own
   types/vitest.d.ts): an empty-bodied interface `extends` is the whole
   point here, and the `any` matches @vitest/expect's own `Assertion<T = any>`
   exactly, or the merge silently fails to apply instead of erroring. */
declare module "vitest" {
  interface Assertion<T = any> extends matchersStandalone.TestingLibraryMatchers<any, T> {}
  interface AsymmetricMatchersContaining
    extends matchersStandalone.TestingLibraryMatchers<any, any> {}
}
/* eslint-enable @typescript-eslint/no-explicit-any, @typescript-eslint/no-empty-object-type */
