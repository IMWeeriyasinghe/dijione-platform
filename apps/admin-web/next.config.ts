import type { NextConfig } from "next";

// Next.js "Multi Zones" pattern: admin-web is mounted at /admin (basePath)
// so its own generated page/asset URLs never collide with shell-web's or
// talent-web's when shell-web proxies /admin/:path* here (CR §12/§14).
// Internal navigation (next/link, next/image) gets basePath applied
// automatically; the API rewrites below opt out of that via
// `basePath: false` since fetch() calls are always bare `/api/...` paths,
// both when this app runs standalone (its own :3001) and when reached
// through shell-web's gateway.
const nextConfig: NextConfig = {
  basePath: "/admin",
  transpilePackages: ["@dijione/design-system", "@dijione/auth-client", "@dijione/contracts"],
  async rewrites() {
    return [
      { source: "/api/auth/:path*", destination: "http://localhost:8000/api/auth/:path*", basePath: false },
      { source: "/api/notifications/:path*", destination: "http://localhost:8000/api/notifications/:path*", basePath: false },
      { source: "/api/admin/:path*", destination: "http://localhost:8001/api/admin/:path*", basePath: false },
    ];
  },
};

export default nextConfig;
