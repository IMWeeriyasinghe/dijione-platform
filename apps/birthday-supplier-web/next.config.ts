import type { NextConfig } from "next";

// Independently deployable supplier-facing app (Phase-Next §6) — a
// separate Next.js zone from birthday-web, its own port, its own build.
// It only ever talks to birthday-api's /api/birthday/portal/* prefix —
// never /api/birthday/orders or /api/birthday/suppliers (internal-only
// paths), enforced by convention: this app's lib/api.ts has no function
// that calls anything else.
const nextConfig: NextConfig = {
  transpilePackages: ["@dijione/design-system", "@dijione/contracts"],
  async rewrites() {
    return [
      { source: "/api/birthday/portal/:path*", destination: "http://localhost:8003/api/birthday/portal/:path*" },
      { source: "/api/birthday/internal/dev/:path*", destination: "http://localhost:8003/api/birthday/internal/dev/:path*" },
    ];
  },
};

export default nextConfig;
