import type { NextConfig } from "next";

// Next.js "Multi Zones" pattern — see apps/admin-web/next.config.ts for the
// full rationale. birthday-web is mounted at /birthday.
const nextConfig: NextConfig = {
  basePath: "/birthday",
  transpilePackages: ["@dijione/design-system", "@dijione/auth-client", "@dijione/contracts"],
  async rewrites() {
    return [
      { source: "/api/auth/:path*", destination: "http://localhost:8000/api/auth/:path*", basePath: false },
      { source: "/api/notifications/:path*", destination: "http://localhost:8000/api/notifications/:path*", basePath: false },
      { source: "/api/birthday/:path*", destination: "http://localhost:8003/api/birthday/:path*", basePath: false },
    ];
  },
};

export default nextConfig;
