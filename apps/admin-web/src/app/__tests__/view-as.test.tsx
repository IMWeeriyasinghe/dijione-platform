import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useParams: () => ({ id: "42" }),
  useRouter: () => ({ refresh: vi.fn(), push: vi.fn() }),
}));

const auth = vi.hoisted(() => ({ me: null as null | Record<string, unknown>, startViewAs: vi.fn() }));
vi.mock("@dijione/auth-client", async (orig) => ({
  ...(await orig<typeof import("@dijione/auth-client")>()),
  useOptionalAuth: () => (auth.me ? { user: auth.me, loading: false, login: vi.fn(), logout: vi.fn() } : null),
  startViewAs: auth.startViewAs,
}));

const api = vi.hoisted(() => ({
  getAdminUser: vi.fn(), listAdminRoles: vi.fn(), listAdminModules: vi.fn(), listAdminClients: vi.fn(),
  getEffectiveAccess: vi.fn(), listAdminGroups: vi.fn(), getAdminGroup: vi.fn(), listAdminAudit: vi.fn(),
}));
vi.mock("@/lib/api", async (orig) => ({ ...(await orig<typeof import("@/lib/api")>()), ...api }));

import { ApiError } from "@dijione/auth-client";
import Page from "../users/[id]/page";

const SUPER = { id: 1, platform_role: "SUPER_ADMIN", platform_permissions: ["platform.admin.access", "platform.admin.view_as"] };
const TARGET = { id: 42, email: "t@example.com", full_name: "Test Person", title: null, platform_role: "PLATFORM_USER",
  is_active: true, identity_provider: "ENTRA", entra_object_id: "o", last_login_at: null, created_at: "2026-01-01T00:00:00Z",
  module_assignments: [] };
const EFFECTIVE = { user_id: 42, full_name: "Test Person", platform_role: "PLATFORM_USER", is_active: true, platform_permissions: [],
  modules: [{ module_key: "talent-flow", module_name: "DijiTalentFlow", enabled: true, role: "TA_MEMBER", role_name: "TA Member",
    client_scope: { all_clients: false, client_ids: [1], client_names: ["ABC Company"] }, permissions: ["a", "b", "c"], sources: [] }] };

function open() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><Page /></QueryClientProvider>);
}

beforeEach(() => {
  Object.values(api).forEach((f) => f.mockReset());
  auth.startViewAs.mockReset();
  auth.me = SUPER;
  api.getAdminUser.mockResolvedValue(TARGET);
  api.listAdminRoles.mockResolvedValue([]);
  api.listAdminModules.mockResolvedValue([]);
  api.listAdminClients.mockResolvedValue([]);
  api.getEffectiveAccess.mockResolvedValue(EFFECTIVE);
  api.listAdminGroups.mockResolvedValue([]);
  api.listAdminAudit.mockResolvedValue([]);
});

describe("View as", () => {
  it("is offered to a Super Admin with the permission and shows what the employee can access", async () => {
    open();
    fireEvent.click(await screen.findByRole("button", { name: /View as/ }));
    const access = await screen.findByTestId("view-as-access");
    expect(access).toHaveTextContent("DijiTalentFlow");
    expect(access).toHaveTextContent("TA Member");
    expect(access).toHaveTextContent("3 permissions");
    expect(access).toHaveTextContent("ABC Company");
    expect(screen.getByText(/session is read-only/i)).toBeInTheDocument();
  });

  it.each([
    ["an administrator without the Super Admin role", { ...SUPER, platform_role: "PLATFORM_ADMIN" }],
    ["a Super Admin without the permission", { ...SUPER, platform_permissions: ["platform.admin.access"] }],
    ["the person's own page", { ...SUPER, id: 42 }],
    ["no signed-in context", null],
  ])("is not offered to %s", async (_label, me) => {
    auth.me = me as typeof auth.me;
    open();
    await screen.findByText("Test Person");
    expect(screen.queryByRole("button", { name: /View as/ })).toBeNull();
  });

  it("is not offered for an inactive person", async () => {
    api.getAdminUser.mockResolvedValue({ ...TARGET, is_active: false });
    open();
    await screen.findByText("Test Person");
    expect(screen.queryByRole("button", { name: /View as/ })).toBeNull();
  });

  it("starts the session for this person and comes back to this page afterwards", async () => {
    auth.startViewAs.mockResolvedValue(undefined);
    open();
    fireEvent.click(await screen.findByRole("button", { name: /View as/ }));
    fireEvent.click(await screen.findByRole("button", { name: "Start read-only session" }));
    await waitFor(() => expect(auth.startViewAs).toHaveBeenCalledWith(42, expect.stringContaining("/")));
  });

  it("shows the server's reason when it cannot start", async () => {
    auth.startViewAs.mockRejectedValue(new ApiError(404, "That user cannot be viewed: choose an active internal employee"));
    open();
    fireEvent.click(await screen.findByRole("button", { name: /View as/ }));
    fireEvent.click(await screen.findByRole("button", { name: "Start read-only session" }));
    expect(await screen.findByText(/cannot be viewed/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Start read-only session" })).toBeEnabled(); // can try again or cancel
  });

  it("says plainly when the person has no access to show", async () => {
    api.getEffectiveAccess.mockResolvedValue({ ...EFFECTIVE, modules: [] });
    open();
    fireEvent.click(await screen.findByRole("button", { name: /View as/ }));
    expect(await screen.findByText(/empty home page/)).toBeInTheDocument();
  });
});
