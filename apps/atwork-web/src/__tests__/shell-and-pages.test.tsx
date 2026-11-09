import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { AtworkContent, buildSections } from "@/app/atwork-shell";
import ManagementPage from "@/app/management/page";
import { PERM, resolveAtworkScope, type AtworkMe, type AtworkScope } from "@/lib/atwork-scope";

const EMPLOYEE: AtworkScope = { role: "ATWORK_USER", permissions: [PERM.ACCESS, PERM.READ_OWN, PERM.RECORD_OWN, PERM.REQUEST_OWN] };
const retry = vi.fn();
const scopeMock = vi.hoisted(() => ({ value: {} as { loading: boolean; failed: boolean; scope: AtworkScope | null } }));
vi.mock("@/lib/atwork-scope", async (orig) => {
  const actual = await orig<typeof import("@/lib/atwork-scope")>();
  return { ...actual, useAtworkScope: () => ({ ...scopeMock.value, retry }) };
});
vi.mock("@dijione/design-system", async (orig) => {
  const actual = await orig<typeof import("@dijione/design-system")>();
  return { ...actual, AppShell: ({ title, children }: { title: string; children: React.ReactNode }) => <main aria-label={title}>{children}</main> };
});
const set = (scope: AtworkScope | null, over: Partial<{ loading: boolean; failed: boolean }> = {}) => { scopeMock.value = { loading: false, failed: false, scope, ...over }; };
const me = (over: Partial<AtworkMe>): AtworkMe => ({ user_id: 1, full_name: "A", module_access: true, role: "R", permissions: [PERM.ACCESS], ...over });
beforeEach(() => { retry.mockClear(); set(EMPLOYEE); });

describe("resolveAtworkScope", () => {
  it("fails closed", () => {
    expect(resolveAtworkScope(undefined)).toBeNull();
    expect(resolveAtworkScope(me({ module_access: false }))).toBeNull();
    expect(resolveAtworkScope(me({ permissions: [] }))).toBeNull();
  });
});

describe("navigation follows permissions", () => {
  const labels = (scope: AtworkScope | null) => buildSections(scope).flatMap((s) => s.items.map((i) => i.label));
  it("shows employee items only for an employee", () => {
    expect(labels(EMPLOYEE)).toEqual(["Today", "My Attendance", "My Requests"]);
  });
  it("gives a manager-named role nothing without permissions", () => {
    expect(labels({ role: "ATWORK_MANAGER", permissions: [PERM.ACCESS] })).toEqual([]);
  });
  it("shows only the Management sections granted", () => {
    expect(labels({ role: "X", permissions: [PERM.MANAGEMENT, PERM.REPORTS] })).toEqual(["Overview", "Reports"]);
  });
});

describe("access states", () => {
  const content = () => render(<AtworkContent><p>protected</p></AtworkContent>);
  it("shows loading without content", () => { set(null, { loading: true }); content(); expect(screen.queryByText("protected")).not.toBeInTheDocument(); });
  it("explains missing access", () => { set(null); content(); expect(screen.getByText("No DijiAtWork access")).toBeInTheDocument(); });
  it("reports an outage as an error and can retry", () => { set(null, { failed: true }); content(); fireEvent.click(screen.getByRole("button")); expect(retry).toHaveBeenCalledOnce(); });
  it("renders content with access", () => { content(); expect(screen.getByText("protected")).toBeInTheDocument(); });
  it("restricts Management without the permission", () => { render(<ManagementPage />); expect(screen.getByText("Management access required")).toBeInTheDocument(); });
});
