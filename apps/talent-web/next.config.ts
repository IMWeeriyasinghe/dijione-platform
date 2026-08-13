import type { NextConfig } from "next";

// Next.js "Multi Zones" pattern — see apps/admin-web/next.config.ts for the
// full rationale. talent-web is mounted at /talent-flow.
const nextConfig: NextConfig = {
  basePath: "/talent-flow",
  transpilePackages: ["@dijione/design-system", "@dijione/auth-client", "@dijione/contracts"],
  async rewrites() {
    return [
      { source: "/api/auth/:path*", destination: "http://localhost:8000/api/auth/:path*", basePath: false },
      { source: "/api/notifications/:path*", destination: "http://localhost:8000/api/notifications/:path*", basePath: false },
      { source: "/api/talent/:path*", destination: "http://localhost:8002/api/talent/:path*", basePath: false },
    ];
  },
};

export default nextConfig;
