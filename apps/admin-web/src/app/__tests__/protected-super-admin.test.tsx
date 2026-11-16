import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useParams: () => ({ id: "42" }),
  useRouter: () => ({ refresh: vi.fn(), push: vi.fn() }),
}));

const auth = vi.hoisted(() => ({ me: null as null | Record<string, unknown> }));
vi.mock("@dijione/auth-client", async (orig) => ({
  ...(await orig<typeof import("@dijione/auth-client")>()),
  useOptionalAuth: () => (auth.me ? { user: auth.me, loading: false, login: vi.fn(), logout: vi.fn() } : null),
}));

const api = vi.hoisted(() => ({
  getAdminUser: vi.fn(), listAdminRoles: vi.fn(), listAdminModules: vi.fn(), listAdminClients: vi.fn(),
  getEffectiveAccess: vi.fn(), listAdminGroups: vi.fn(), getAdminGroup: vi.fn(), listAdminAudit: vi.fn(),
}));
vi.mock("@/lib/api", async (orig) => ({ ...(await orig<typeof import("@/lib/api")>()), ...api }));

import Page from "../users/[id]/page";

const OTHER_ADMIN = { id: 1, platform_role: "SUPER_ADMIN", platform_permissions: ["platform.admin.access", "platform.admin.view_as"] };
const USER = { id: 42, email: "m@example.com", full_name: "Protected Person", title: null, platform_role: "SUPER_ADMIN",
  is_active: true, identity_provider: "ENTRA", entra_object_id: "o", last_login_at: null, created_at: "2026-01-01T00:00:00Z",
  module_assignments: [] };

function open() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><Page /></QueryClientProvider>);
}

beforeEach(() => {
  Object.values(api).forEach((f) => f.mockReset());
  auth.me = OTHER_ADMIN;
  api.listAdminRoles.mockResolvedValue([]);
  api.listAdminModules.mockResolvedValue([]);
  api.listAdminClients.mockResolvedValue([]);
  api.getEffectiveAccess.mockResolvedValue(null);
  api.listAdminGroups.mockResolvedValue([]);
  api.listAdminAudit.mockResolvedValue([]);
});

describe("Protected Super Admin", () => {
  it("locks the role, shows the label and the explanation, and blocks deactivation", async () => {
    api.getAdminUser.mockResolvedValue({ ...USER, protected: true });
    open();
    expect(await screen.findByTestId("protected-super-admin")).toHaveTextContent("Protected Super Admin");
    expect(screen.getByLabelText("Platform role")).toBeDisabled();
    expect(screen.getByText(/privilege is protected and cannot be removed by other administrators/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Deactivate" })).toBeDisabled();
  });

  it("leaves an ordinary account's role editable", async () => {
    api.getAdminUser.mockResolvedValue({ ...USER, platform_role: "PLATFORM_USER", protected: false });
    open();
    expect(await screen.findByLabelText("Platform role")).toBeEnabled();
    expect(screen.queryByTestId("protected-super-admin")).toBeNull();
    expect(screen.getByRole("button", { name: "Deactivate" })).toBeEnabled();
  });
});
