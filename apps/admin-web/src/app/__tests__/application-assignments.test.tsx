import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";

// Application detail page (generic over modules): role choice comes from the
// role catalog for the module, nothing is pre-selected, assignments can be
// edited in place, and Client Scope appears only for modules whose
// authorization reads it (registry flag supports_client_scope). "field-ops"
// is a fictional module standing in for any module without client scope.
const nav = vi.hoisted(() => ({ key: "field-ops" }));
vi.mock("next/navigation", () => ({
  useParams: () => ({ key: nav.key }),
  useRouter: () => ({ refresh: vi.fn(), push: vi.fn() }),
}));

const api = vi.hoisted(() => ({
  getApplicationDetail: vi.fn(),
  listAdminRoles: vi.fn(),
  listAdminClients: vi.fn(),
  listAdminUsers: vi.fn(),
  listAdminGroups: vi.fn(),
  upsertModuleAssignment: vi.fn(),
  upsertGroupModuleAssignment: vi.fn(),
}));
vi.mock("@/lib/api", async (orig) => ({ ...(await orig<typeof import("@/lib/api")>()), ...api }));

import Page from "../applications/[key]/page";

const ROLES = [
  { id: 1, key: "TA_MEMBER", name: "TA Member", module_key: "talent-flow", description: "", permission_count: 1 },
  { id: 2, key: "FIELD_ADMIN", name: "Field Admin", module_key: "field-ops", description: "", permission_count: 7 },
  { id: 3, key: "FIELD_VIEWER", name: "Field Viewer", module_key: "field-ops", description: "", permission_count: 3 },
];
const SCOPE_ALL = { all_clients: true, client_ids: [], client_names: [] };

function detail(supports: boolean, extra: object = {}) {
  return {
    module_key: nav.key, module_name: supports ? "DijiTalentFlow" : "Field Ops", description: "", status: "ACTIVE",
    enabled: true, assigned_users: [], assigned_groups: [], direct_user_count: 0, group_count: 0,
    supports_client_scope: supports, ...extra,
  };
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}><Page /></QueryClientProvider>);
}

beforeEach(() => {
  Object.values(api).forEach((f) => f.mockReset());
  nav.key = "field-ops";
  api.listAdminRoles.mockResolvedValue(ROLES);
  api.listAdminClients.mockResolvedValue([{ id: 7, name: "Acme" }]);
  api.listAdminUsers.mockResolvedValue([{ id: 42, full_name: "Test Person", email: "test.person@example.com" }]);
  api.listAdminGroups.mockResolvedValue([{ id: 9, display_name: "Ops Team" }]);
  api.upsertModuleAssignment.mockResolvedValue({});
  api.upsertGroupModuleAssignment.mockResolvedValue({});
});

const optionLabels = (select: HTMLElement) => within(select).getAllByRole("option").map((o) => o.textContent);

describe("module without client scope (generic)", () => {
  it("offers both module roles, pre-selects none and hides Client Scope", async () => {
    api.getApplicationDetail.mockResolvedValue(detail(false));
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: /assign user/i }));
    const role = screen.getByLabelText(/^Role/);
    expect(optionLabels(role)).toEqual(["Select a role…", "Field Admin", "Field Viewer"]);
    expect((role as HTMLSelectElement).value).toBe("");
    expect(screen.queryByText("Client Scope")).not.toBeInTheDocument();
    expect(screen.queryByText("All Clients")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Assign" })).toBeDisabled();
  });

  it("assigns Field Viewer", async () => {
    api.getApplicationDetail.mockResolvedValue(detail(false));
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: /assign user/i }));
    fireEvent.change(screen.getByLabelText(/^User/), { target: { value: "42" } });
    fireEvent.change(screen.getByLabelText(/^Role/), { target: { value: "FIELD_VIEWER" } });
    fireEvent.click(screen.getByRole("button", { name: "Assign" }));
    await waitFor(() =>
      expect(api.upsertModuleAssignment).toHaveBeenCalledWith(42, "field-ops", { role: "FIELD_VIEWER", enabled: true, client_scope: undefined }),
    );
  });

  it("assigns Field Admin", async () => {
    api.getApplicationDetail.mockResolvedValue(detail(false));
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: /assign user/i }));
    fireEvent.change(screen.getByLabelText(/^User/), { target: { value: "42" } });
    fireEvent.change(screen.getByLabelText(/^Role/), { target: { value: "FIELD_ADMIN" } });
    fireEvent.click(screen.getByRole("button", { name: "Assign" }));
    await waitFor(() => expect(api.upsertModuleAssignment).toHaveBeenCalledWith(42, "field-ops", expect.objectContaining({ role: "FIELD_ADMIN" })));
  });

  it("edits an existing assignment in place (Admin -> Viewer)", async () => {
    api.getApplicationDetail.mockResolvedValue(detail(false, {
      assigned_users: [{ user_id: 42, full_name: "Test Person", email: "test.person@example.com", role: "FIELD_ADMIN",
        role_name: "Field Admin", enabled: true, client_scope: SCOPE_ALL }],
      direct_user_count: 1,
    }));
    renderPage();
    expect(await screen.findByText("Field Admin")).toBeInTheDocument();
    expect(screen.queryByRole("columnheader", { name: "Client Scope" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /edit assignment for test person/i }));
    const role = screen.getByLabelText(/^Role/) as HTMLSelectElement;
    expect(role.value).toBe("FIELD_ADMIN");
    expect(optionLabels(role)).toEqual(["Field Admin", "Field Viewer"]);
    fireEvent.change(role, { target: { value: "FIELD_VIEWER" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() =>
      expect(api.upsertModuleAssignment).toHaveBeenCalledWith(42, "field-ops", { role: "FIELD_VIEWER", enabled: true, client_scope: undefined }),
    );
  });

  it("group assignment offers both roles without Client Scope", async () => {
    api.getApplicationDetail.mockResolvedValue(detail(false));
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: /assign group/i }));
    expect(optionLabels(screen.getByLabelText(/^Role/))).toEqual(["Select a role…", "Field Admin", "Field Viewer"]);
    expect(screen.queryByText("Client Scope")).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText(/^Group/), { target: { value: "9" } });
    fireEvent.change(screen.getByLabelText(/^Role/), { target: { value: "FIELD_VIEWER" } });
    fireEvent.click(screen.getByRole("button", { name: "Assign" }));
    await waitFor(() =>
      expect(api.upsertGroupModuleAssignment).toHaveBeenCalledWith(9, "field-ops", { role: "FIELD_VIEWER", enabled: true, client_scope: undefined }),
    );
  });
});

describe("client-scoped modules keep Client Scope", () => {
  it("TalentFlow shows Client Scope and sends it", async () => {
    nav.key = "talent-flow";
    api.getApplicationDetail.mockResolvedValue(detail(true));
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: /assign user/i }));
    expect(optionLabels(screen.getByLabelText(/^Role/))).toEqual(["Select a role…", "TA Member"]);
    expect(screen.getByText("Client Scope")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText(/^User/), { target: { value: "42" } });
    fireEvent.change(screen.getByLabelText(/^Role/), { target: { value: "TA_MEMBER" } });
    fireEvent.click(screen.getByLabelText("All Clients"));
    fireEvent.click(screen.getByLabelText("Acme"));
    fireEvent.click(screen.getByRole("button", { name: "Assign" }));
    await waitFor(() =>
      expect(api.upsertModuleAssignment).toHaveBeenCalledWith(42, "talent-flow", {
        role: "TA_MEMBER", enabled: true, client_scope: { all_clients: false, client_ids: [7] },
      }),
    );
  });
});
