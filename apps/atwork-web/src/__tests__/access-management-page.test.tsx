import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

// The shared page (packages/design-system) with its API client replaced: what it shows and what
// it sends. Platform Core's own tests cover the authorization decisions.
const api = vi.hoisted(() => ({
  me: vi.fn(), users: vi.fn(), people: vi.fn(), grant: vi.fn(), onboard: vi.fn(), revokePreview: vi.fn(),
  revoke: vi.fn(), liftSuspension: vi.fn(), admins: vi.fn(), user: vi.fn(), appoint: vi.fn(), removeAdmin: vi.fn(),
}));
vi.mock("@dijione/auth-client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@dijione/auth-client")>()),
  accessApi: () => api,
}));

import { ApiError } from "@dijione/auth-client";
import { AccessManagementPage } from "@dijione/design-system";

const ME = {
  module_key: "atwork", module_name: "DijiAtWork", is_admin: true, can_appoint_admins: false,
  supports_client_scope: false, grantable_roles: [{ key: "ATWORK_MANAGER", name: "DijiAtWork Manager" }],
  client_authority: null, default_role_name: "DijiAtWork User",
};
const source = (type: string, extra = {}) => ({
  type, role: "ATWORK_MANAGER", role_name: "DijiAtWork Manager", group_id: null, group_name: null, mandated: false,
  applies: true, scope: null, ...extra,
});
const person = (id: number, name: string, extra = {}) => ({
  user_id: id, full_name: name, email: `${name.toLowerCase()}@example.com`, title: null, is_active: true,
  eligible_employee: true, has_access: true, role: "ATWORK_MANAGER", role_name: "DijiAtWork Manager", sources: [],
  suspension: null, administrator: null, manageable: true, managed_reason: null, ...extra,
});

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <AccessManagementPage moduleKey="atwork" appName="DijiAtWork" />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  Object.values(api).forEach((fn) => fn.mockReset());
  api.me.mockResolvedValue(ME);
  api.users.mockResolvedValue({ users: [], default_access_note: null });
});

describe("AccessManagementPage", () => {
  it("explains that only appointed administrators can manage access", async () => {
    api.me.mockResolvedValue({ ...ME, is_admin: false });
    renderPage();
    expect(await screen.findByText("You are not an access administrator")).toBeInTheDocument();
    expect(api.users).not.toHaveBeenCalled();
  });

  it("explains View-as and a switched-off feature instead of failing", async () => {
    api.me.mockRejectedValue(new ApiError(404, "Not Found"));
    renderPage();
    expect(await screen.findByText(/not available for this application/)).toBeInTheDocument();
  });

  it("shows every source, marks mandatory access, and only offers actions it may take", async () => {
    api.users.mockResolvedValue({
      default_access_note: "Every eligible employee has DijiAtWork User access.",
      users: [
        person(1, "David", { sources: [source("DIRECT"), source("BASELINE", { role_name: "DijiAtWork User", mandated: true })] }),
        person(2, "Gina", { manageable: false, managed_reason: "Outside your authority: managed in Central Admin." }),
      ],
    });
    renderPage();
    expect(await screen.findByText("David")).toBeInTheDocument();
    expect(screen.getByText("Every eligible employee has DijiAtWork User access.")).toBeInTheDocument();
    expect(screen.getByText(/Every employee · DijiAtWork User \(mandatory\)/)).toBeInTheDocument();
    expect(screen.getByText("Outside your authority: managed in Central Admin.")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Remove" })).toHaveLength(1); // Gina has none
  });

  it("adds a directory employee and grants a role", async () => {
    api.people.mockResolvedValue({
      directory_available: true,
      people: [{ user_id: null, entra_object_id: "oid-1", full_name: "Nina", email: "nina@example.com", job_title: null,
        department: null, source: "DIRECTORY", has_access: false, role_name: null, can_grant: true, reason: null }],
    });
    api.onboard.mockResolvedValue(person(9, "Nina"));
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: /Add person/ }));
    fireEvent.change(screen.getByLabelText("Search employees"), { target: { value: "nin" } });
    fireEvent.click(await screen.findByRole("button", { name: "Select" }, { timeout: 2000 }));
    fireEvent.click(screen.getByRole("button", { name: "Save access" }));
    await waitFor(() => expect(api.onboard).toHaveBeenCalledWith("oid-1", { role: "ATWORK_MANAGER" }));
  });

  it("previews a removal, including what is suspended and what stays, then removes with a reason", async () => {
    api.users.mockResolvedValue({ users: [person(1, "David", { sources: [source("DIRECT")] })], default_access_note: null });
    api.revokePreview.mockResolvedValue({
      allowed: true, reason: null, removes_direct: source("DIRECT"),
      suspends: [source("GROUP", { group_name: "Ops" })],
      keeps: [source("BASELINE", { role_name: "DijiAtWork User", mandated: true })],
    });
    api.revoke.mockResolvedValue(person(1, "David", { has_access: true }));
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "Remove" }));
    expect(await screen.findByText(/Suspends, in this application only/)).toHaveTextContent("Ops (DijiAtWork Manager)");
    expect(screen.getByText(/Keeps mandatory access/)).toHaveTextContent("Every employee (DijiAtWork User)");
    fireEvent.change(screen.getByLabelText(/Reason/), { target: { value: "Moved team" } });
    fireEvent.click(screen.getByRole("button", { name: "Remove access" }));
    await waitFor(() => expect(api.revoke).toHaveBeenCalledWith(1, "Moved team"));
  });

  it("does not offer a removal the server refuses, and shows why", async () => {
    api.users.mockResolvedValue({ users: [person(1, "David", { sources: [source("DIRECT")] })], default_access_note: null });
    api.revokePreview.mockResolvedValue({ allowed: false, reason: "Includes access outside your authority: ask Central Admin.",
      removes_direct: null, suspends: [], keeps: [] });
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "Remove" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("outside your authority");
    expect(screen.queryByRole("button", { name: "Remove access" })).not.toBeInTheDocument();
  });
});
