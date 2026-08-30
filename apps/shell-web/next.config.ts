import type { NextConfig } from "next";

// DijiOne Shell is the single public entry point (CR §14): the browser only
// ever talks to shell-web's origin. Page requests for /admin, /talent-flow,
// /birthday are proxied to their own independently-runnable Next.js apps;
// API requests are proxied to the owning backend service.
//
// Every upstream is environment-driven with a localhost default, so LOCAL /
// DEV / UAT / PROD differ only by environment variables — never by editing
// this file. In Azure, these point at the internal Container App addresses;
// production may instead front them with Azure Front Door / API Management
// doing the same path-based fan-out (docs/platform/service-architecture.md).
const up = (name: string, fallback: string): string => process.env[name] ?? fallback;

const ADMIN_WEB_URL = up("ADMIN_WEB_URL", "http://localhost:3001");
const TALENT_WEB_URL = up("TALENT_WEB_URL", "http://localhost:3002");
const BIRTHDAY_WEB_URL = up("BIRTHDAY_WEB_URL", "http://localhost:3003");
const PLATFORM_API_URL = up("PLATFORM_API_URL", "http://localhost:8000");
const ADMIN_API_URL = up("ADMIN_API_URL", "http://localhost:8001");
const TALENT_API_URL = up("TALENT_API_URL", "http://localhost:8002");
const BIRTHDAY_API_URL = up("BIRTHDAY_API_URL", "http://localhost:8003");
const SPARK_API_URL = up("SPARK_API_URL", "http://localhost:8004");

const nextConfig: NextConfig = {
  output: "standalone",
  transpilePackages: ["@dijione/design-system", "@dijione/auth-client", "@dijione/contracts"],
  async rewrites() {
    return [
      { source: "/admin", destination: `${ADMIN_WEB_URL}/admin` },
      { source: "/admin/:path*", destination: `${ADMIN_WEB_URL}/admin/:path*` },
      { source: "/talent-flow", destination: `${TALENT_WEB_URL}/talent-flow` },
      { source: "/talent-flow/:path*", destination: `${TALENT_WEB_URL}/talent-flow/:path*` },
      { source: "/birthday", destination: `${BIRTHDAY_WEB_URL}/birthday` },
      { source: "/birthday/:path*", destination: `${BIRTHDAY_WEB_URL}/birthday/:path*` },

      { source: "/api/auth/:path*", destination: `${PLATFORM_API_URL}/api/auth/:path*` },
      { source: "/api/modules", destination: `${PLATFORM_API_URL}/api/modules` },
      { source: "/api/notifications/:path*", destination: `${PLATFORM_API_URL}/api/notifications/:path*` },
      { source: "/api/admin/:path*", destination: `${ADMIN_API_URL}/api/admin/:path*` },
      { source: "/api/talent/:path*", destination: `${TALENT_API_URL}/api/talent/:path*` },
      { source: "/api/birthday/:path*", destination: `${BIRTHDAY_API_URL}/api/birthday/:path*` },
      { source: "/api/spark/:path*", destination: `${SPARK_API_URL}/api/spark/:path*` },
    ];
  },
};

export default nextConfig;
