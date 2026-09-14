import type { NextConfig } from "next";
import pkg from "./package.json";

// The Client Talent Review Workspace — a separate, constrained Next.js
// zone from the internal talent-web. Its own port, its own build, NOT
// proxied through shell-web. It only ever talks to talent-api's
// /api/talent/external/* prefix (redeem + the client-safe read routes) —
// never any internal /api/talent/* path. That boundary is enforced by
// convention: this app's lib/api.ts has no function that calls anything
// else. Upstream is environment-driven with a localhost default.
const up = (name: string, fallback: string): string => process.env[name] ?? fallback;

const TALENT_API_URL = up("TALENT_API_URL", "http://localhost:8002");

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
      {
        source: "/api/talent/external/:path*",
        destination: `${TALENT_API_URL}/api/talent/external/:path*`,
      },
    ];
  },
};

export default nextConfig;
