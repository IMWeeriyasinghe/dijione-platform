import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useParams: () => ({ id: "42" }),
  useRouter: () => ({ refresh: vi.fn(), push: vi.fn() }),
}));

const auth = vi.hoisted(() => ({ me: null as null | Record<string, unknown>, photo: null as string | null }));
vi.mock("@dijione/auth-client", async (orig) => ({
  ...(await orig<typeof import("@dijione/auth-client")>()),
  useOptionalAuth: () => (auth.me ? { user: auth.me, loading: false, login: vi.fn(), logout: vi.fn() } : null),
  useAuthorizedImage: (path: string | null) => (path ? auth.photo : null),
  startViewAs: vi.fn(),
}));

const api = vi.hoisted(() => ({
  getAdminUser: vi.fn(), listAdminRoles: vi.fn(), listAdminModules: vi.fn(), listAdminClients: vi.fn(),
  getEffectiveAccess: vi.fn(), listAdminGroups: vi.fn(), getAdminGroup: vi.fn(), listAdminAudit: vi.fn(),
  verifyUserWithDirectory: vi.fn(), getEntraGroups: vi.fn(),
}));
vi.mock("@/lib/api", async (orig) => ({ ...(await orig<typeof import("@/lib/api")>()), ...api }));

import Page from "../users/[id]/page";

const SUPER = { id: 1, platform_role: "SUPER_ADMIN", platform_permissions: ["platform.admin.access", "platform.admin.view_as"] };
const BASE = { id: 42, email: "isuru@example.com", full_name: "Isuru Solomons", title: null, platform_role: "PLATFORM_USER",
  is_active: true, identity_provider: "ENTRA", entra_object_id: null, last_login_at: null, created_at: "2026-11-16T00:00:00Z",
  module_assignments: [], directory_verified: false, verification_source: "NONE", employee_record: null,
  eligible_employee: false, signed_in: false, employee_number: null };
const VERIFIED = { ...BASE, entra_object_id: "00000001-0000-4000-8000-000000000000", directory_verified: true,
  verification_source: "DIRECTORY", employee_record: "MATCHED", eligible_employee: true, employee_number: "0107" };

function open() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><Page /></QueryClientProvider>);
}

beforeEach(() => {
  Object.values(api).forEach((f) => f.mockReset());
  auth.me = SUPER;
  auth.photo = null;
  api.listAdminRoles.mockResolvedValue([]);
  api.listAdminModules.mockResolvedValue([]);
  api.listAdminClients.mockResolvedValue([]);
  api.getEffectiveAccess.mockResolvedValue({ platform_permissions: [], modules: [], default_access_excluded: [] });
  api.listAdminGroups.mockResolvedValue([]);
  api.listAdminAudit.mockResolvedValue([]);
});

describe("Employee identity", () => {
  it("shows a provisioned, unverified profile and verifies it with the directory", async () => {
    api.getAdminUser.mockResolvedValue(BASE);
    api.verifyUserWithDirectory.mockResolvedValue(VERIFIED);
    open();
    const badges = await screen.findByTestId("identity-badges");
    expect(badges).toHaveTextContent("Awaiting directory verification");
    expect(badges).toHaveTextContent("Provisioned, not yet signed in");
    fireEvent.click(screen.getByRole("button", { name: /verify with directory/i }));
    await waitFor(() => expect(api.verifyUserWithDirectory).toHaveBeenCalledWith(42));
  });

  it("shows a verified, matched employee before their first sign-in", async () => {
    api.getAdminUser.mockResolvedValue(VERIFIED);
    open();
    const card = await screen.findByTestId("identity-card");
    expect(card).toHaveTextContent("Directory verified");
    expect(card).toHaveTextContent("In BambooHR");
    expect(card).toHaveTextContent("0107");
    expect(card).toHaveTextContent("Eligible");
    expect(screen.queryByRole("button", { name: /verify with directory/i })).not.toBeInTheDocument();
  });

  it("uses the Microsoft 365 photo when there is one, otherwise initials", async () => {
    api.getAdminUser.mockResolvedValue(VERIFIED);
    auth.photo = "blob:photo";
    open();
    expect(await screen.findByTestId("avatar-photo")).toHaveAttribute("src", "blob:photo");
  });

  it("falls back to initials without a photo", async () => {
    api.getAdminUser.mockResolvedValue(BASE);
    open();
    await screen.findByTestId("identity-badges");
    expect(screen.queryByTestId("avatar-photo")).not.toBeInTheDocument();
    expect(screen.getAllByTestId("avatar-initials")[0]).toHaveTextContent("IS");
  });
});

describe("View as before the first sign-in", () => {
  it("is offered for a verified employee who has never signed in", async () => {
    api.getAdminUser.mockResolvedValue(VERIFIED);
    open();
    fireEvent.click(await screen.findByRole("button", { name: /view as/i }));
    expect(screen.getByRole("button", { name: /start read-only session/i })).toBeEnabled();
  });

  it("only previews access for an unverified profile", async () => {
    api.getAdminUser.mockResolvedValue(BASE);
    open();
    fireEvent.click(await screen.findByRole("button", { name: /preview access/i }));
    expect(screen.getByTestId("view-as-preview-only")).toHaveTextContent(/verify this profile with the directory/i);
    expect(screen.getByRole("button", { name: /start read-only session/i })).toBeDisabled();
  });

  it("only previews access for an identity without an employee record", async () => {
    api.getAdminUser.mockResolvedValue({ ...VERIFIED, employee_record: "NOT_FOUND", eligible_employee: false });
    open();
    fireEvent.click(await screen.findByRole("button", { name: /preview access/i }));
    expect(screen.getByTestId("view-as-preview-only")).toHaveTextContent(/bamboohr employee record/i);
  });
});

describe("Entra Groups", () => {
  it("lists memberships read only and separately from DijiOne groups", async () => {
    api.getAdminUser.mockResolvedValue(VERIFIED);
    api.getEntraGroups.mockResolvedValue([
      { object_id: "g-1", display_name: "All Staff", group_type: "Microsoft 365", membership: "DIRECT", dijione_mapping: null },
      { object_id: "g-2", display_name: "Engineering", group_type: "Security", membership: "INHERITED", dijione_mapping: null },
    ]);
    open();
    fireEvent.click(await screen.findByRole("button", { name: "Entra Groups" }));
    expect(await screen.findByText("All Staff")).toBeInTheDocument();
    expect(screen.getByText("Inherited")).toBeInTheDocument();
    expect(screen.getByText(/do not grant any DijiOne access/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /add|remove/i })).not.toBeInTheDocument();
  });
});
