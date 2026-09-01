import type { NextConfig } from "next";

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
  async rewrites() {
    return [
      { source: "/api/auth/:path*", destination: `${PLATFORM_API_URL}/api/auth/:path*`, basePath: false },
      { source: "/api/notifications/:path*", destination: `${PLATFORM_API_URL}/api/notifications/:path*`, basePath: false },
      { source: "/api/birthday/:path*", destination: `${BIRTHDAY_API_URL}/api/birthday/:path*`, basePath: false },
    ];
  },
};

export default nextConfig;
