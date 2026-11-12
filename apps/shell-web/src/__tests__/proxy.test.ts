import { describe, expect, it } from "vitest";
import { NextRequest } from "next/server";
import { canonicalPath, proxy } from "@/proxy";

const status = (path: string) => proxy(new NextRequest(`https://x.example${path}`)).status;
const req = (pathname: string) => ({ nextUrl: { pathname } }) as unknown as NextRequest;

describe("gateway internal-route block", () => {
  it.each([
    "/api/atwork/internal",
    "/api/atwork/internal/",
    "/api/atwork/internal/notifications/run",
    "/api/atwork/INTERNAL/x",
    "/api/atwork/%69nternal/x",
    "/api/atwork/%2569nternal/x",
    "/api/atwork/%252569nternal/x",
    "/api/atwork//internal/x",
    "/api/atwork/./internal/x",
    "/api/atwork/x/../internal/x",
    "/api/atwork/x/%2e%2e/internal/x",
    "/api/atwork\\internal/x",
    "/api/atwork/internal%2Fx",
    "/api/atwork/internal;a=b/x",
  ])("blocks %s", (path) => expect(proxy(req(path)).status).toBe(404));

  it("refuses paths that cannot be decoded", () => expect(proxy(req("/api/atwork/%E0%A4%A")).status).toBe(400));
  it("refuses excessive encoding", () => expect(canonicalPath(`/${"%25".repeat(9)}41`)).toBeNull());

  it.each(["/api/atwork/metadata", "/api/atwork/attendance/status", "/api/atwork/internals", "/api/atwork/management/corrections/internal"])(
    "passes %s",
    (path) => expect(status(path)).toBe(200),
  );
});
