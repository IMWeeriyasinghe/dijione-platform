import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";

const perms = vi.hoisted(() => ({ set: new Set<string>() }));
vi.mock("@dijione/auth-client", async (orig) => ({
  ...(await orig<typeof import("@dijione/auth-client")>()),
  useAuth: () => ({ user: { id: 1 } }),
  usePlatformPermission: (p: string) => perms.set.has(p),
}));
const api = vi.hoisted(() => ({
  listApplicationAdministrators: vi.fn(),
  listApplicationSuspensions: vi.fn(),
  appointApplicationAdministrator: vi.fn(),
  removeApplicationAdministrator: vi.fn(),
  liftApplicationSuspension: vi.fn(),
  setModuleEnabled: vi.fn(),
}));
vi.mock("@/lib/api", async (orig) => ({ ...(await orig<typeof import("@/lib/api")>()), ...api }));

import { DelegatedAccessSection } from "../applications/[key]/delegated-access";

const APP = {
  module_key: "talent-flow", module_name: "DijiTalentFlow", description: "", status: "ACTIVE", enabled: true,
  assigned_users: [], assigned_groups: [], direct_user_count: 0, group_count: 0, supports_client_scope: true,
  delegation_supported: true, delegable_roles: [{ key: "TA_MEMBER", name: "TA Member" }, { key: "TA_MANAGER", name: "TA Manager" }],
};
const USERS = [
  { id: 1, full_name: "Super", email: "s@x", eligible_employee: true },
  { id: 7, full_name: "Tom", email: "tom@x", eligible_employee: true },
  { id: 8, full_name: "Outsider", email: "o@x", eligible_employee: false },
] as never[];

function show() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <DelegatedAccessSection app={APP} users={USERS} clients={[{ id: 1, name: "ABC Company" }]} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  Object.values(api).forEach((f) => f.mockReset());
  api.listApplicationAdministrators.mockResolvedValue([]);
  api.listApplicationSuspensions.mockResolvedValue([
    { user_id: 9, full_name: "David", email: "d@x", reason: "Left team", suspended_by_name: "Tom", suspended_at: "2026-11-18" },
  ]);
  perms.set = new Set();
});

describe("Central Admin: delegated application access", () => {
  it("a Super Admin appoints an eligible employee with explicit role and client authority", async () => {
    perms.set = new Set(["platform.admin.manage_admins", "platform.admin.manage_users"]);
    api.appointApplicationAdministrator.mockResolvedValue({});
    show();
    fireEvent.click(await screen.findByRole("button", { name: "Appoint administrator" }));
    const options = Array.from(screen.getByLabelText(/Employee/).querySelectorAll("option")).map((o) => o.textContent);
    expect(options).toContain("Tom (tom@x)");
    expect(options).not.toContain("Outsider (o@x)"); // not eligible
    fireEvent.change(screen.getByLabelText(/Employee/), { target: { value: "7" } });
    fireEvent.click(screen.getByLabelText("TA Member"));
    fireEvent.click(screen.getByLabelText("ABC Company"));
    fireEvent.click(screen.getByRole("button", { name: "Appoint" }));
    await waitFor(() =>
      expect(api.appointApplicationAdministrator).toHaveBeenCalledWith("talent-flow", 7, {
        grantable_roles: ["TA_MEMBER"], client_authority: { all_clients: false, client_ids: [1] },
      }),
    );
  });

  it("appointing yourself needs a break-glass reason", async () => {
    perms.set = new Set(["platform.admin.manage_admins"]);
    show();
    fireEvent.click(await screen.findByRole("button", { name: "Appoint administrator" }));
    fireEvent.change(screen.getByLabelText(/Employee/), { target: { value: "1" } });
    fireEvent.click(screen.getByLabelText("TA Member"));
    fireEvent.click(screen.getByLabelText("ABC Company"));
    expect(screen.getByRole("button", { name: "Appoint" })).toBeDisabled();
    fireEvent.change(screen.getByLabelText(/Break-glass reason/), { target: { value: "Covering during outage" } });
    expect(screen.getByRole("button", { name: "Appoint" })).toBeEnabled();
  });

  it("a Platform Admin sees administrators and suspensions but cannot appoint; can lift a suspension", async () => {
    perms.set = new Set(["platform.admin.manage_users"]);
    api.liftApplicationSuspension.mockResolvedValue({ status: "lifted" });
    show();
    expect(await screen.findByText("David")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Appoint administrator" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Disable application/ })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Lift suspension" }));
    await waitFor(() => expect(api.liftApplicationSuspension).toHaveBeenCalledWith("talent-flow", 9));
  });
});
