import { NextResponse, type NextRequest } from "next/server";

const INTERNAL = /^\/api\/atwork\/internal(\/|$)/i;
const MAX_DECODES = 5;

/** Reduces a path to the form a downstream router would see, however it was encoded. */
export function canonicalPath(raw: string): string | null {
  let path = raw;
  for (let i = 0; ; i++) {
    let decoded: string;
    try {
      decoded = decodeURIComponent(path);
    } catch {
      return null;
    }
    if (decoded === path) break;
    if (i === MAX_DECODES) return null;
    path = decoded;
  }
  const parts: string[] = [];
  for (const part of path.replace(/\\/g, "/").split("/")) {
    if (part === "" || part === ".") continue;
    if (part === "..") parts.pop();
    else parts.push(part.split(";")[0]);
  }
  return `/${parts.join("/")}`;
}

// DijiAtWork's internal routes are service-to-service only. A rewrite rule matches
// the encoded path, so anything that cannot be reduced safely is refused too.
export function proxy(request: NextRequest) {
  const path = canonicalPath(request.nextUrl.pathname);
  if (path === null) return new NextResponse(null, { status: 400 });
  if (INTERNAL.test(path)) return new NextResponse(null, { status: 404 });
  return NextResponse.next();
}

export const config = { matcher: "/api/atwork/:path*" };
