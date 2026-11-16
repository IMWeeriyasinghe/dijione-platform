import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";

// Users -> Applications editor (generic): a new assignment for a module with
// several roles never defaults to the first (alphabetically most privileged)
// role; existing assignments keep their role. "field-ops" is a fictional
// module without client scope; "solo" has a single role.
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
  upsertModuleAssignment: vi.fn(),
  removeModuleAssignment: vi.fn(),
  restoreDefaultAccess: vi.fn(),
}));
vi.mock("@/lib/api", async (orig) => ({ ...(await orig<typeof import("@/lib/api")>()), ...api }));

import Page from "../users/[id]/page";

const MODULES = [
  { id: 1, key: "field-ops", name: "Field Ops", description: "", icon: "Box", route: "/f", status: "ACTIVE", enabled: true,
    display_order: 1, user_count: 0, supports_client_scope: false },
  { id: 2, key: "solo", name: "Solo App", description: "", icon: "Box", route: "/s", status: "ACTIVE", enabled: true,
    display_order: 2, user_count: 0, supports_client_scope: true },
];
const ROLES = [
  { id: 1, key: "FIELD_ADMIN", name: "Field Admin", module_key: "field-ops", description: "", permission_count: 7 },
  { id: 2, key: "FIELD_VIEWER", name: "Field Viewer", module_key: "field-ops", description: "", permission_count: 3 },
  { id: 3, key: "SOLO_USER", name: "Solo User", module_key: "solo", description: "", permission_count: 1 },
];

function user(assignments: object[] = []) {
  return { id: 42, email: "t@example.com", full_name: "Test Person", title: null, platform_role: "PLATFORM_USER",
    is_active: true, identity_provider: "entra", entra_object_id: null, last_login_at: null, created_at: "2026-01-01T00:00:00Z",
    module_assignments: assignments };
}

async function openApplications() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><Page /></QueryClientProvider>);
  fireEvent.click(await screen.findByRole("button", { name: "Applications" }));
  const card = (name: string) => screen.getByText(name).closest("div.p-5, [class*='p-5']") as HTMLElement;
  return { field: card("Field Ops"), solo: card("Solo App") };
}

beforeEach(() => {
  Object.values(api).forEach((f) => f.mockReset());
  api.listAdminRoles.mockResolvedValue(ROLES);
  api.listAdminModules.mockResolvedValue(MODULES);
  api.listAdminClients.mockResolvedValue([]);
  api.getEffectiveAccess.mockResolvedValue({ module_roles: [] });
  api.listAdminGroups.mockResolvedValue([]);
  api.listAdminAudit.mockResolvedValue([]);
  api.upsertModuleAssignment.mockResolvedValue(user());
});

describe("Users -> Applications role selection", () => {
  it("new multi-role assignment: no role pre-selected, Save disabled until chosen, no Client Scope", async () => {
    api.getAdminUser.mockResolvedValue(user());
    const { field } = await openApplications();
    fireEvent.click(within(field).getByLabelText("Enabled"));
    const role = within(field).getByRole("combobox") as HTMLSelectElement;
    expect(role.value).toBe("");
    expect(within(role).getAllByRole("option").map((o) => o.textContent)).toEqual(["Select a role…", "Field Admin", "Field Viewer"]);
    expect(within(field).queryByText("Client Scope")).not.toBeInTheDocument();
    const save = within(field).getByRole("button", { name: /save field ops access/i });
    expect(save).toBeDisabled();
    fireEvent.change(role, { target: { value: "FIELD_VIEWER" } });
    expect(save).toBeEnabled();
    fireEvent.click(save);
    await waitFor(() =>
      expect(api.upsertModuleAssignment).toHaveBeenCalledWith(42, "field-ops", { role: "FIELD_VIEWER", enabled: true, client_scope: undefined }),
    );
  });

  it("single-role module still selects its only role", async () => {
    api.getAdminUser.mockResolvedValue(user());
    const { solo } = await openApplications();
    expect((within(solo).getByRole("combobox") as HTMLSelectElement).value).toBe("SOLO_USER");
  });

  it("existing assignment keeps its role when toggling Enabled and can switch role in place", async () => {
    api.getAdminUser.mockResolvedValue(user([{ module_key: "field-ops", role: "FIELD_ADMIN", enabled: true,
      client_scope: { all_clients: true, client_ids: [], client_names: [] } }]));
    const { field } = await openApplications();
    const role = within(field).getByRole("combobox") as HTMLSelectElement;
    expect(role.value).toBe("FIELD_ADMIN");
    expect(within(role).queryByText("Select a role…")).not.toBeInTheDocument();
    fireEvent.click(within(field).getByLabelText("Enabled")); // disable
    fireEvent.click(within(field).getByRole("button", { name: /save field ops access/i }));
    await waitFor(() => expect(api.upsertModuleAssignment).toHaveBeenLastCalledWith(42, "field-ops",
      { role: "FIELD_ADMIN", enabled: false, client_scope: undefined }));
    fireEvent.click(within(field).getByLabelText("Enabled")); // re-enable
    fireEvent.change(role, { target: { value: "FIELD_VIEWER" } });
    fireEvent.click(within(field).getByRole("button", { name: /save field ops access/i }));
    await waitFor(() => expect(api.upsertModuleAssignment).toHaveBeenLastCalledWith(42, "field-ops",
      { role: "FIELD_VIEWER", enabled: true, client_scope: undefined }));
  });
});

// D5: a specific scope with no client selected would be stored as unrestricted.
describe("Users -> Applications client scope", () => {
  it("cannot save a specific client scope until a client is selected", async () => {
    api.getAdminUser.mockResolvedValue(user());
    api.listAdminClients.mockResolvedValue([{ id: 7, name: "Acme" }]);
    const { solo } = await openApplications();
    fireEvent.click(within(solo).getByLabelText("Enabled"));
    const save = within(solo).getByRole("button", { name: /save solo app access/i });
    expect(save).toBeEnabled();

    fireEvent.click(within(solo).getByLabelText("All Clients"));
    expect(save).toBeDisabled();
    expect(within(solo).getByText("Select at least one client, or choose All Clients.")).toBeInTheDocument();
    fireEvent.click(save);
    expect(api.upsertModuleAssignment).not.toHaveBeenCalled();

    fireEvent.click(within(solo).getByLabelText("Acme"));
    expect(save).toBeEnabled();
    fireEvent.click(save);
    await waitFor(() =>
      expect(api.upsertModuleAssignment).toHaveBeenCalledWith(42, "solo", {
        role: "SOLO_USER", enabled: true, client_scope: { all_clients: false, client_ids: [7] },
      }),
    );
  });
});

// Default employee access is always on: shown, never removable from here.
describe("Users -> Applications default employee access", () => {
  const effective = (over: object) => ({ platform_permissions: [], modules: [], default_access_excluded: [], ...over });

  it("shows the always-on default access without any way to remove it", async () => {
    api.getAdminUser.mockResolvedValue(user());
    api.getEffectiveAccess.mockResolvedValue(effective({
      modules: [{ module_key: "field-ops", module_name: "Field Ops", enabled: true, role: "FIELD_VIEWER", role_name: "Field Viewer",
        client_scope: { all_clients: true, client_ids: [], client_names: [] }, permissions: [],
        sources: [{ type: "BASELINE", role: "FIELD_VIEWER", group_id: null, group_name: null }] }],
    }));
    await openApplications();
    expect(await screen.findByTestId("default-access-note")).toHaveTextContent(/field ops standard access \(field viewer\)/i);
    expect(screen.getByTestId("default-access-note")).toHaveTextContent(/always on and cannot be removed/i);
    expect(screen.queryByRole("button", { name: /remove default access/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /restore default access/i })).not.toBeInTheDocument();
    expect(api.removeModuleAssignment).not.toHaveBeenCalled();
  });

  it("shows no default-access control for an application without one", async () => {
    api.getAdminUser.mockResolvedValue(user());
    api.getEffectiveAccess.mockResolvedValue(effective({}));
    await openApplications();
    expect(screen.queryByRole("button", { name: /default access/i })).not.toBeInTheDocument();
  });

  it("loads the audit history for this user, not only account events", async () => {
    api.getAdminUser.mockResolvedValue(user());
    await openApplications();
    await waitFor(() => expect(api.listAdminAudit).toHaveBeenCalledWith({ user_id: 42 }));
  });
});
