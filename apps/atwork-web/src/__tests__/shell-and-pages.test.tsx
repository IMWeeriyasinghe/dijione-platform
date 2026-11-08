import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { AtworkContent, buildSections } from "@/app/atwork-shell";
import ManagementPage from "@/app/management/page";
import HistoryPage from "@/app/history/page";
import HomePage from "@/app/page";
import TodayPage from "@/app/today/page";
import { PERM, resolveAtworkScope, type AtworkMe, type AtworkScope } from "@/lib/atwork-scope";

const USER: AtworkScope = { role: "ATWORK_USER", permissions: [PERM.ACCESS] };
const MANAGER: AtworkScope = { role: "ATWORK_MANAGER", permissions: [PERM.ACCESS, PERM.MANAGEMENT] };

const retry = vi.fn();
const scopeMock = vi.hoisted(() => ({ value: {} as { loading: boolean; failed: boolean; scope: AtworkScope | null } }));
vi.mock("@/lib/atwork-scope", async (orig) => {
  const actual = await orig<typeof import("@/lib/atwork-scope")>();
  return { ...actual, useAtworkScope: () => ({ ...scopeMock.value, retry }) };
});
vi.mock("@dijione/design-system", async (orig) => {
  const actual = await orig<typeof import("@dijione/design-system")>();
  return {
    ...actual,
    AppShell: ({ title, children }: { title: string; children: React.ReactNode }) => <main aria-label={title}>{children}</main>,
  };
});

const set = (scope: AtworkScope | null, over: Partial<{ loading: boolean; failed: boolean }> = {}) => {
  scopeMock.value = { loading: false, failed: false, scope, ...over };
};
const me = (over: Partial<AtworkMe>): AtworkMe => ({
  user_id: 1, full_name: "A", module_access: true, role: "R", permissions: [PERM.ACCESS], ...over,
});

beforeEach(() => {
  retry.mockClear();
  set(USER);
});

describe("resolveAtworkScope", () => {
  it("fails closed", () => {
    expect(resolveAtworkScope(undefined)).toBeNull();
    expect(resolveAtworkScope(me({ module_access: false }))).toBeNull();
    expect(resolveAtworkScope(me({ permissions: [] }))).toBeNull();
    expect(resolveAtworkScope(me({ permissions: ["atwork.other"] }))).toBeNull();
  });
  it("keeps role and permissions", () => {
    expect(resolveAtworkScope(me({}))).toEqual({ role: "R", permissions: [PERM.ACCESS] });
  });
});

describe("navigation", () => {
  const labels = (scope: AtworkScope | null) => buildSections(scope).flatMap((s) => s.items.map((i) => i.label));
  it("hides Management without the permission, even for a manager-named role", () => {
    expect(labels(USER)).toEqual(["Home", "Today", "My History"]);
    expect(labels({ role: "ATWORK_MANAGER", permissions: [PERM.ACCESS] })).not.toContain("Management");
  });
  it("shows Management with the permission", () => {
    expect(labels(MANAGER)).toContain("Management");
  });
});

describe("access states", () => {
  const content = () => render(<AtworkContent><p>protected</p></AtworkContent>);

  it("shows loading without content", () => {
    set(null, { loading: true });
    content();
    expect(screen.getByText("Checking access…")).toBeInTheDocument();
    expect(screen.queryByText("protected")).not.toBeInTheDocument();
  });
  it("explains missing access", () => {
    set(null);
    content();
    expect(screen.getByText("No DijiAtWork access")).toBeInTheDocument();
    expect(screen.queryByText("protected")).not.toBeInTheDocument();
  });
  it("reports an outage as an error, not as missing access, and can retry", () => {
    set(null, { failed: true });
    content();
    expect(screen.queryByText("No DijiAtWork access")).not.toBeInTheDocument();
    expect(screen.queryByText("protected")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button"));
    expect(retry).toHaveBeenCalledOnce();
  });
  it("renders content with access", () => {
    content();
    expect(screen.getByText("protected")).toBeInTheDocument();
  });
});

describe("pages are placeholders only", () => {
  it("home lists the sections and omits Management for users", () => {
    render(<HomePage />);
    expect(screen.getByRole("heading", { name: "Today" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "My History" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Management" })).not.toBeInTheDocument();
  });
  it.each([["Today", TodayPage], ["My History", HistoryPage]])("%s is not functional yet", (title, Page) => {
    render(<Page />);
    expect(screen.getByRole("heading", { name: title })).toBeInTheDocument();
    expect(screen.getByText("Not available yet")).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
  it("Management is restricted without the permission", () => {
    render(<ManagementPage />);
    expect(screen.getByText("Management access required")).toBeInTheDocument();
    expect(screen.queryByText("Not available yet")).not.toBeInTheDocument();
  });
  it("Management shows its placeholder with the permission", () => {
    set(MANAGER);
    render(<ManagementPage />);
    expect(screen.getByText("Not available yet")).toBeInTheDocument();
  });
});
