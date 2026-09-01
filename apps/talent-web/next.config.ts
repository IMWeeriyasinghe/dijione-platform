import type { NextConfig } from "next";

// Next.js "Multi Zones" pattern — see apps/admin-web/next.config.ts for the
// full rationale. talent-web is mounted at /talent-flow. Upstreams are
// environment-driven with a localhost default (no source edits per env).
const up = (name: string, fallback: string): string => process.env[name] ?? fallback;

const PLATFORM_API_URL = up("PLATFORM_API_URL", "http://localhost:8000");
const TALENT_API_URL = up("TALENT_API_URL", "http://localhost:8002");

const nextConfig: NextConfig = {
  basePath: "/talent-flow",
  output: "standalone",
  transpilePackages: ["@dijione/design-system", "@dijione/auth-client", "@dijione/contracts"],
  async rewrites() {
    return [
      { source: "/api/auth/:path*", destination: `${PLATFORM_API_URL}/api/auth/:path*`, basePath: false },
      { source: "/api/notifications/:path*", destination: `${PLATFORM_API_URL}/api/notifications/:path*`, basePath: false },
      { source: "/api/talent/:path*", destination: `${TALENT_API_URL}/api/talent/:path*`, basePath: false },
    ];
  },
};

export default nextConfig;
