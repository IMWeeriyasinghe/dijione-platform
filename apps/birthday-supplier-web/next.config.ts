import type { NextConfig } from "next";
import pkg from "./package.json";

// Independently deployable supplier-facing app (Phase-Next §6) — a
// separate Next.js zone from birthday-web, its own port, its own build.
// It only ever talks to birthday-api's /api/birthday/portal/* prefix —
// never /api/birthday/orders or /api/birthday/suppliers (internal-only
// paths), enforced by convention: this app's lib/api.ts has no function
// that calls anything else. Upstream is environment-driven with a
// localhost default (no source edits per environment).
const up = (name: string, fallback: string): string => process.env[name] ?? fallback;

const BIRTHDAY_API_URL = up("BIRTHDAY_API_URL", "http://localhost:8003");

const nextConfig: NextConfig = {
  output: "standalone",
  transpilePackages: ["@dijione/design-system", "@dijione/contracts"],
  // Per-app footer version/build metadata (docs/platform/versioning.md) —
  // version always comes from THIS app's own package.json, never a shared
  // platform-wide value; GIT_SHA/BUILD_DATE come from the Docker build args
  // deploy/Dockerfile.web sets (dev default "dev"/"unknown" for `next dev`).
  env: {
    NEXT_PUBLIC_APP_VERSION: pkg.version,
    NEXT_PUBLIC_GIT_SHA: up("GIT_SHA", "dev"),
    NEXT_PUBLIC_BUILD_DATE: up("BUILD_DATE", ""),
  },
  async rewrites() {
    return [
      { source: "/api/birthday/portal/:path*", destination: `${BIRTHDAY_API_URL}/api/birthday/portal/:path*` },
      { source: "/api/birthday/internal/dev/:path*", destination: `${BIRTHDAY_API_URL}/api/birthday/internal/dev/:path*` },
      // Supplier Entra sign-in config + the code exchange. The /login and
      // /api/auth/callback routes are handled by this app's own route.ts
      // (filesystem routes win over rewrites).
      { source: "/api/birthday/supplier/auth/:path*", destination: `${BIRTHDAY_API_URL}/api/birthday/supplier/auth/:path*` },
    ];
  },
};

export default nextConfig;
