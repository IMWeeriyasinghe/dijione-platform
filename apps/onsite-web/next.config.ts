import type { NextConfig } from "next";
import pkg from "./package.json";

// Next.js "Multi Zones" pattern — see apps/admin-web/next.config.ts for the
// full rationale. onsite-web is mounted at /onsite. It talks ONLY to the
// shared Platform Core (auth, notifications) and its own onsite-api — never
// to another application module (docs/onsite/architecture.md).
const up = (name: string, fallback: string): string => process.env[name] ?? fallback;

const PLATFORM_API_URL = up("PLATFORM_API_URL", "http://localhost:8000");
const ONSITE_API_URL = up("ONSITE_API_URL", "http://localhost:8008");

const nextConfig: NextConfig = {
  basePath: "/onsite",
  output: "standalone",
  transpilePackages: ["@dijione/design-system", "@dijione/auth-client", "@dijione/contracts"],
  env: {
    NEXT_PUBLIC_APP_VERSION: pkg.version,
    NEXT_PUBLIC_GIT_SHA: up("GIT_SHA", "dev"),
    NEXT_PUBLIC_BUILD_DATE: up("BUILD_DATE", ""),
  },
  async rewrites() {
    return [
      { source: "/api/auth/:path*", destination: `${PLATFORM_API_URL}/api/auth/:path*`, basePath: false },
      { source: "/api/notifications/:path*", destination: `${PLATFORM_API_URL}/api/notifications/:path*`, basePath: false },
      { source: "/api/onsite/:path*", destination: `${ONSITE_API_URL}/api/onsite/:path*`, basePath: false },
    ];
  },
};

export default nextConfig;
