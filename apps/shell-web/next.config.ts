import type { NextConfig } from "next";

// DijiOne Shell is the single public entry point in local dev (CR §14):
// the browser only ever talks to :3000. Page requests for /admin and
// /talent-flow are proxied to their own independently-runnable Next.js
// apps; API requests are proxied to the owning backend service. Production
// swaps this rewrite layer for Azure Front Door/APIM doing the same
// path-based fan-out — see docs/platform/service-architecture.md.
const nextConfig: NextConfig = {
  transpilePackages: ["@dijione/design-system", "@dijione/auth-client", "@dijione/contracts"],
  async rewrites() {
    return [
      { source: "/admin", destination: "http://localhost:3001/admin" },
      { source: "/admin/:path*", destination: "http://localhost:3001/admin/:path*" },
      { source: "/talent-flow", destination: "http://localhost:3002/talent-flow" },
      { source: "/talent-flow/:path*", destination: "http://localhost:3002/talent-flow/:path*" },
      { source: "/_next/:path*", destination: "http://localhost:3000/_next/:path*" },

      { source: "/api/auth/:path*", destination: "http://localhost:8000/api/auth/:path*" },
      { source: "/api/modules", destination: "http://localhost:8000/api/modules" },
      { source: "/api/notifications/:path*", destination: "http://localhost:8000/api/notifications/:path*" },
      { source: "/api/admin/:path*", destination: "http://localhost:8001/api/admin/:path*" },
      { source: "/api/talent/:path*", destination: "http://localhost:8002/api/talent/:path*" },
      { source: "/api/birthday/:path*", destination: "http://localhost:8003/api/birthday/:path*" },
      { source: "/api/spark/:path*", destination: "http://localhost:8004/api/spark/:path*" },
    ];
  },
};

export default nextConfig;
