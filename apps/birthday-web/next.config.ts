import type { NextConfig } from "next";
import pkg from "./package.json";

// Next.js "Multi Zones" pattern — see apps/admin-web/next.config.ts for the
// full rationale. birthday-web is mounted at /birthday. Upstreams are
// environment-driven with a localhost default (no source edits per env).
const up = (name: string, fallback: string): string => process.env[name] ?? fallback;

const PLATFORM_API_URL = up("PLATFORM_API_URL", "http://localhost:8000");
const BIRTHDAY_API_URL = up("BIRTHDAY_API_URL", "http://localhost:8003");

const nextConfig: NextConfig = {
  basePath: "/birthday",
  output: "standalone",
  transpilePackages: ["@dijione/design-system", "@dijione/auth-client", "@dijione/contracts"],
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
      { source: "/api/auth/:path*", destination: `${PLATFORM_API_URL}/api/auth/:path*`, basePath: false },
      { source: "/api/notifications/:path*", destination: `${PLATFORM_API_URL}/api/notifications/:path*`, basePath: false },
      { source: "/api/birthday/:path*", destination: `${BIRTHDAY_API_URL}/api/birthday/:path*`, basePath: false },
    ];
  },
};

export default nextConfig;
