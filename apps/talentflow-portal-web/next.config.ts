import type { NextConfig } from "next";

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
