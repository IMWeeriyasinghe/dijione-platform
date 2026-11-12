import { NextResponse } from "next/server";

/**
 * Exposes this container's own runtime RELEASE_DATE (docs/platform/
 * versioning.md) and APP_ENV-derived is_production flag — genuinely
 * evaluated fresh per request, never baked into the build. `force-dynamic`
 * is the provable guarantee: most of this app's routes are statically
 * prerendered at build time (confirmed via this app's own `next build`
 * output), so a plain `process.env` read inside a page/layout risks being
 * baked once at build time rather than read at request time. A Route
 * Handler explicitly marked force-dynamic has no such ambiguity — it
 * always executes against the live, standalone Node server
 * (`output: "standalone"`) for every request.
 *
 * `is_production` in particular MUST be runtime, not a NEXT_PUBLIC_* build
 * arg: this platform builds one image and promotes the exact same digest
 * DEV -> UAT -> PROD (deploy/README.md) — a build-time value would be
 * wrong the moment that same image runs in a different environment.
 * Gates whether the birthday-web sidebar shows the non-production-only
 * Email Safety admin nav item (birthday-shell.tsx) — the corresponding,
 * independent backend enforcement is
 * apps/birthday-api/app/api/deps.py's require_non_production().
 *
 * Served at `/birthday/api/meta` (this app's own basePath, see
 * next.config.ts) — reached the same way whether hit directly or proxied
 * through the DijiOne shell's `/birthday/:path*` wildcard rewrite.
 */
export const dynamic = "force-dynamic";

export function GET() {
  return NextResponse.json({
    release_date: process.env.RELEASE_DATE ?? null,
    is_production: process.env.APP_ENV === "prod",
  });
}
