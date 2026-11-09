import type { NextConfig } from "next";
import pkg from "./package.json";

// Next.js "Multi Zones" pattern: atwork-web is mounted at /atwork. It talks
// only to the shared Platform Core (auth, notifications) and its own atwork-api.
const up = (name: string, fallback: string): string => process.env[name] ?? fallback;

const PLATFORM_API_URL = up("PLATFORM_API_URL", "http://localhost:8000");
const ATWORK_API_URL = up("ATWORK_API_URL", "http://localhost:8009");

const nextConfig: NextConfig = {
  basePath: "/atwork",
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
      { source: "/api/atwork/:path*", destination: `${ATWORK_API_URL}/api/atwork/:path*`, basePath: false },
    ];
  },
};

export default nextConfig;
