import type { NextConfig } from "next";

// Next.js "Multi Zones" pattern: admin-web is mounted at /admin (basePath)
// so its own generated page/asset URLs never collide with shell-web's or
// talent-web's when shell-web proxies /admin/:path* here (CR §12/§14).
// Internal navigation (next/link, next/image) gets basePath applied
// automatically; the API rewrites below opt out of that via
// `basePath: false` since fetch() calls are always bare `/api/...` paths,
// both when this app runs standalone (its own :3001) and when reached
// through shell-web's gateway. Upstreams are environment-driven with a
// localhost default (no source edits per environment).
const up = (name: string, fallback: string): string => process.env[name] ?? fallback;

const PLATFORM_API_URL = up("PLATFORM_API_URL", "http://localhost:8000");
const ADMIN_API_URL = up("ADMIN_API_URL", "http://localhost:8001");

const nextConfig: NextConfig = {
  basePath: "/admin",
  output: "standalone",
  transpilePackages: ["@dijione/design-system", "@dijione/auth-client", "@dijione/contracts"],
  async rewrites() {
    return [
      { source: "/api/auth/:path*", destination: `${PLATFORM_API_URL}/api/auth/:path*`, basePath: false },
      { source: "/api/notifications/:path*", destination: `${PLATFORM_API_URL}/api/notifications/:path*`, basePath: false },
      { source: "/api/admin/:path*", destination: `${ADMIN_API_URL}/api/admin/:path*`, basePath: false },
    ];
  },
};

export default nextConfig;
