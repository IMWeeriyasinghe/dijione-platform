import { NextResponse, type NextRequest } from "next/server";

// DijiAtWork's internal routes are service-to-service only. A rewrite rule matches
// the encoded path, so decode here to catch forms such as /%69nternal/.
export function proxy(request: NextRequest) {
  let path: string;
  try {
    path = decodeURIComponent(request.nextUrl.pathname);
  } catch {
    return new NextResponse(null, { status: 400 });
  }
  if (/^\/api\/atwork\/+internal(\/|$)/i.test(path)) return new NextResponse(null, { status: 404 });
  return NextResponse.next();
}

export const config = { matcher: "/api/atwork/:path*" };
