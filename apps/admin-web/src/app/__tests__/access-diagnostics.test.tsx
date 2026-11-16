import { fireEvent, render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useParams: () => ({ id: "42" }),
  useRouter: () => ({ refresh: vi.fn(), push: vi.fn() }),
}));

const api = vi.hoisted(() => ({
  getAdminUser: vi.fn(),
  listAdminRoles: vi.fn(),
  listAdminModules: vi.fn(),
  listAdminClients: vi.fn(),
  getEffectiveAccess: vi.fn(),
  listAdminGroups: vi.fn(),
  getAdminGroup: vi.fn(),
  listAdminAudit: vi.fn(),
  getAccessDiagnostics: vi.fn(),
}));
vi.mock("@/lib/api", async (orig) => ({ ...(await orig<typeof import("@/lib/api")>()), ...api }));

import Page from "../users/[id]/page";

const DIAG = {
  user_id: 42, full_name: "Test Person", email: "t@example.com",
  account: { is_active: true, identity_provider: "ENTRA", entra_linked: true, internal_employee: false,
    platform_role: "PLATFORM_USER", platform_permissions: [], last_sign_in_at: "2026-11-15T08:00:00Z", created_at: null },
  default_access: [{ module_key: "atwork", module_name: "DijiAtWork", role: "ATWORK_USER", state: "NOT_ELIGIBLE",
    reasons: ["Not verified as an internal employee (set only by a verified Microsoft sign-in)."] }],
  groups: [{ group_id: 1, group_name: "TA Team", status: "INACTIVE", grants: [{ module_key: "talent-flow", role: "TA_MEMBER", enabled: true }] }],
  modules: [{ module_key: "talent-flow", module_name: "DijiTalentFlow", role: "TA_MEMBER", role_name: "TA Member",
    permissions: ["talent.requests.read"],
    sources: [{ type: "GROUP", role: "TA_MEMBER", group_name: "Ops", permissions: ["talent.requests.read"], client_scope: "All clients" }],
    client_scope: { all_clients: true, client_ids: [], client_names: [] }, uses_client_scope: true,
    scope_explanation: "Unrestricted: at least one source gives access to all clients, or has no client limit recorded.",
    inactive: [{ type: "GROUP", role: "TA_MEMBER", group_name: "TA Team", reason: "The group is inactive, so its grants do not apply." }] }],
  session: { last_sign_in_at: "2026-11-15T08:00:00Z", token_issue_time_available: false,
    token_issue_time_note: "Not recorded. Session tokens are verified locally.", access_changes_since_last_sign_in: 2,
    latest_access_change_at: "2026-11-15T09:00:00Z", token_lifetime_minutes: 720 },
  checks: [{ key: "token_freshness", level: "info", message: "Token freshness is unavailable: the platform does not record token issue times." }],
};

async function open() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><Page /></QueryClientProvider>);
  fireEvent.click(await screen.findByRole("button", { name: "Diagnostics" }));
}

beforeEach(() => {
  Object.values(api).forEach((f) => f.mockReset());
  api.getAdminUser.mockResolvedValue({ id: 42, email: "t@example.com", full_name: "Test Person", title: null,
    platform_role: "PLATFORM_USER", is_active: true, identity_provider: "entra", entra_object_id: null,
    last_login_at: null, created_at: "2026-01-01T00:00:00Z", module_assignments: [] });
  api.listAdminRoles.mockResolvedValue([]);
  api.listAdminModules.mockResolvedValue([]);
  api.listAdminClients.mockResolvedValue([]);
  api.getEffectiveAccess.mockResolvedValue({ modules: [], platform_permissions: [] });
  api.listAdminGroups.mockResolvedValue([]);
  api.listAdminAudit.mockResolvedValue([]);
});

describe("Diagnostics tab", () => {
  it("explains sources, scope, default access, groups and marks token freshness unavailable", async () => {
    api.getAccessDiagnostics.mockResolvedValue(DIAG);
    await open();
    const mod = await screen.findByTestId("diag-module-talent-flow");
    expect(within(mod).getByText(/Inherited from Ops gives TA_MEMBER/)).toBeTruthy();
    expect(within(mod).getByText(/Not applied: TA Team TA_MEMBER/)).toBeTruthy();
    expect(within(mod).getByText(/Unrestricted/)).toBeTruthy();
    expect(screen.getByText(/DijiAtWork/)).toBeTruthy();
    expect(screen.getByText(/Not eligible/)).toBeTruthy();
    expect(screen.getByText(/inactive — grants do not apply/)).toBeTruthy();
    expect(screen.getAllByText(/Token freshness: unavailable/).length).toBe(1);
    expect(screen.getByText(/Changes recorded since last sign-in: 2/)).toBeTruthy();
  });

  it("shows an error state when diagnostics cannot be loaded", async () => {
    api.getAccessDiagnostics.mockRejectedValue(new Error("boom"));
    await open();
    expect(await screen.findByText("Could not load access diagnostics.")).toBeTruthy();
  });
});
