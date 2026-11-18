import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const auth = vi.hoisted(() => ({ user: null as unknown }));
vi.mock("@dijione/auth-client", async (orig) => ({
  ...(await orig<typeof import("@dijione/auth-client")>()),
  useAuth: () => ({ user: auth.user }),
}));

import { RoleIndicator, summarizeRoles } from "@dijione/design-system";
import type { CurrentUser } from "@dijione/contracts";

const g = (role: string, role_name: string, source: string, extra = {}) => ({
  role, role_name, source, group_name: null, mandatory: false, administrative: false, ...extra,
});
const USER = {
  id: 1, email: "pat@example.com", full_name: "Pat", title: null, avatar_color: null,
  platform_role: "PLATFORM_ADMIN", platform_role_name: "Platform Admin", platform_permissions: [],
  module_roles: [
    {
      module_key: "talent-flow", role: "TA_MEMBER", role_name: "Talent Acquisition Member", client_id: null,
      grants: [
        g("TA_MEMBER", "Talent Acquisition Member", "DIRECT"),
        g("CUSTOMER_SUCCESS", "Customer Success", "GROUP", { group_name: "CS Team" }),
        g("TALENT_ACCESS_ADMIN", "Access Administrator", "APPOINTMENT", { administrative: true }),
      ],
      client_scope: { all_clients: false, clients: ["ABC Company"] },
    },
    {
      module_key: "atwork", role: "ATWORK_USER", role_name: "DijiAtWork User", client_id: null,
      grants: [g("ATWORK_USER", "DijiAtWork User", "BASELINE", { mandatory: true })], client_scope: null,
    },
  ],
} as unknown as CurrentUser;

beforeEach(() => {
  auth.user = USER;
});

describe("summarizeRoles", () => {
  it("shows the platform role on DijiOne Home and Central Admin", () => {
    expect(summarizeRoles(USER, "platform")).toMatchObject({ primary: "Platform Admin", extra: 0 });
  });

  it("inside an application shows that application's primary role and +N other roles, never the platform role", () => {
    const s = summarizeRoles(USER, "talent-flow")!;
    expect(s.primary).toBe("Talent Acquisition Member");
    expect(s.extra).toBe(2);
    expect(s.business.map((x) => x.role)).toEqual(["TA_MEMBER", "CUSTOMER_SUCCESS"]);
    expect(s.administrative.map((x) => x.role)).toEqual(["TALENT_ACCESS_ADMIN"]);
    expect(s.scope).toBe("ABC Company");
  });

  it("shows nothing for an application the person has no role in", () => {
    expect(summarizeRoles(USER, "onsite")).toBeNull();
  });
});

describe("RoleIndicator", () => {
  it("renders the compact role with +N and an accessible, read-only access summary", () => {
    render(<RoleIndicator context="talent-flow" />);
    const button = screen.getByRole("button", { name: /Your role: Talent Acquisition Member and 2 more/ });
    expect(button).toHaveTextContent("+2");
    expect(button).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(button);
    const panel = screen.getByRole("dialog", { name: "Your access" });
    expect(panel).toHaveTextContent("Customer Success");
    expect(panel).toHaveTextContent("From group: CS Team");
    expect(panel).toHaveTextContent("Clients: ABC Company");
    expect(panel).toHaveTextContent("Administration");
    expect(panel).toHaveTextContent("manages access; no business permissions");
    expect(panel.querySelectorAll("button, input, select")).toHaveLength(0); // nothing to change here
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("marks mandatory access", () => {
    render(<RoleIndicator context="atwork" />);
    fireEvent.click(screen.getByRole("button"));
    expect(screen.getByRole("dialog")).toHaveTextContent("Every employee (mandatory)");
  });

  it("renders nothing when signed out", () => {
    auth.user = null;
    const { container } = render(<RoleIndicator context="platform" />);
    expect(container).toBeEmptyDOMElement();
  });
});
