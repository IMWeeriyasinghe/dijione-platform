import { NextResponse } from "next/server";

/**
 * Exposes this container's own runtime RELEASE_DATE (docs/platform/
 * versioning.md) — genuinely evaluated fresh per request, never baked into
 * the build. `force-dynamic` is the provable guarantee: most of this app's
 * routes are statically prerendered at build time (confirmed via this
 * app's own `next build` output), so a plain `process.env` read inside a
 * page/layout risks being baked once at build time rather than read at
 * request time. A Route Handler explicitly marked force-dynamic has no
 * such ambiguity — it always executes against the live, standalone Node
 * server (`output: "standalone"`) for every request.
 *
 * Served at `/birthday/api/meta` (this app's own basePath, see
 * next.config.ts) — reached the same way whether hit directly or proxied
 * through the DijiOne shell's `/birthday/:path*` wildcard rewrite.
 */
export const dynamic = "force-dynamic";

export function GET() {
  return NextResponse.json({ release_date: process.env.RELEASE_DATE ?? null });
}
