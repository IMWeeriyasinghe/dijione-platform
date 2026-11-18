import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

vi.mock("@dijione/auth-client", () => ({ useTalentScope: vi.fn() }));
vi.mock("@dijione/design-system", () => ({
  AuthGate: ({ children }: { children: ReactNode }) => <>{children}</>,
  EmptyState: ({ title }: { title: string }) => <p data-testid="empty-state">{title}</p>,
  AccessManagementPage: ({ moduleKey }: { moduleKey: string }) => <p data-testid="access-page">{moduleKey}</p>,
  AppShell: ({ topNavTitle, sections, children }: {
    topNavTitle: string; sections: { items: { label: string }[] }[]; children: ReactNode;
  }) => (
    <div>
      <h1>{topNavTitle}</h1>
      <nav data-testid="nav">{sections.flatMap((s) => s.items).map((i) => <span key={i.label}>{i.label}</span>)}</nav>
      <main>{children}</main>
    </div>
  ),
  VersionFooter: () => null,
}));

import { useTalentScope } from "@dijione/auth-client";
import { TalentShell } from "../talent-shell";
import AccessPage from "../access/page";

const scope = vi.mocked(useTalentScope);
const base = { clientId: null, isCustomerSuccessOrManager: false };

describe("DijiTalentFlow access administration", () => {
  it("an access administrator without a business role sees only Access, not the client workspace", () => {
    scope.mockReturnValue({ ...base, role: "TALENT_ACCESS_ADMIN", isStaff: false, isClient: false, canManageAccess: true, accessAdminOnly: true });
    render(<TalentShell><p>dashboard</p></TalentShell>);
    expect(screen.getByRole("heading")).toHaveTextContent("Access Management");
    expect(screen.getByTestId("nav")).toHaveTextContent(/^Access$/);
    expect(screen.getByTestId("access-page")).toHaveTextContent("talent-flow");
    expect(screen.queryByText("dashboard")).not.toBeInTheDocument();
  });

  it("a TA staff administrator keeps the workspace and gains Access", () => {
    scope.mockReturnValue({ ...base, role: "TA_MEMBER", isStaff: true, isClient: false, canManageAccess: true, accessAdminOnly: false });
    render(<TalentShell><p>dashboard</p></TalentShell>);
    expect(screen.getByTestId("nav")).toHaveTextContent("All Requests");
    expect(screen.getByTestId("nav")).toHaveTextContent("Access");
    expect(screen.getByText("dashboard")).toBeInTheDocument();
  });

  it("staff without an appointment get no Access entry and the page refuses", () => {
    scope.mockReturnValue({ ...base, role: "TA_MEMBER", isStaff: true, isClient: false, canManageAccess: false, accessAdminOnly: false });
    render(<TalentShell><AccessPage /></TalentShell>);
    expect(screen.getByTestId("nav")).not.toHaveTextContent(/Access$/);
    expect(screen.getByTestId("empty-state")).toHaveTextContent("Access administration required");
  });
});
