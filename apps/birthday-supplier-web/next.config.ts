import type { NextConfig } from "next";

// Independently deployable supplier-facing app (Phase-Next §6) — a
// separate Next.js zone from birthday-web, its own port, its own build.
// It only ever talks to birthday-api's /api/birthday/portal/* prefix —
// never /api/birthday/orders or /api/birthday/suppliers (internal-only
// paths), enforced by convention: this app's lib/api.ts has no function
// that calls anything else. Upstream is environment-driven with a
// localhost default (no source edits per environment).
const up = (name: string, fallback: string): string => process.env[name] ?? fallback;

const BIRTHDAY_API_URL = up("BIRTHDAY_API_URL", "http://localhost:8003");

const nextConfig: NextConfig = {
  output: "standalone",
  transpilePackages: ["@dijione/design-system", "@dijione/contracts"],
  async rewrites() {
    return [
      { source: "/api/birthday/portal/:path*", destination: `${BIRTHDAY_API_URL}/api/birthday/portal/:path*` },
      { source: "/api/birthday/internal/dev/:path*", destination: `${BIRTHDAY_API_URL}/api/birthday/internal/dev/:path*` },
    ];
  },
};

export default nextConfig;
