import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/lib/api", () => ({ getReleaseMetadata: vi.fn().mockResolvedValue({ release_date: null, is_production: true }) }));
vi.mock("@dijione/auth-client", () => ({ useBirthdayScope: vi.fn() }));
vi.mock("@dijione/design-system", () => ({
  AuthGate: ({ children }: { children: ReactNode }) => <>{children}</>,
  EmptyState: ({ title }: { title: string }) => <p data-testid="empty-state">{title}</p>,
  AccessManagementPage: ({ moduleKey }: { moduleKey: string }) => <p data-testid="access-page">{moduleKey}</p>,
  AppShell: ({ sections, children }: { sections: { items: { label: string }[] }[]; children: ReactNode }) => (
    <div>
      <nav data-testid="nav">{sections.flatMap((s) => s.items).map((i) => <span key={i.label}>{i.label}</span>)}</nav>
      <main data-testid="main">{children}</main>
    </div>
  ),
  VersionFooter: () => null,
}));

import { useBirthdayScope } from "@dijione/auth-client";
import { BirthdayShell } from "../birthday-shell";
import AccessPage from "../admin/access/page";

const scope = vi.mocked(useBirthdayScope);
const wrap = (ui: ReactNode) =>
  render(<QueryClientProvider client={new QueryClient()}>{ui}</QueryClientProvider>);

describe("DIJI Birthday staff access administration", () => {
  it("an access administrator without a business role sees only Staff Access and never the business pages", () => {
    scope.mockReturnValue({ role: "BIRTHDAY_ACCESS_ADMIN", isAdmin: false, canManageAccess: true, accessAdminOnly: true });
    wrap(<BirthdayShell><p>orders page</p></BirthdayShell>);
    expect(screen.getByTestId("nav")).toHaveTextContent(/^Staff Access$/);
    expect(screen.getByTestId("access-page")).toHaveTextContent("birthday");
    expect(screen.queryByText("orders page")).not.toBeInTheDocument();
  });

  it("an administrator with a business role keeps the business navigation and gains Staff Access", () => {
    scope.mockReturnValue({ role: "BIRTHDAY_ADMIN", isAdmin: true, canManageAccess: true, accessAdminOnly: false });
    wrap(<BirthdayShell><p>orders page</p></BirthdayShell>);
    expect(screen.getByTestId("nav")).toHaveTextContent("Cake Orders");
    expect(screen.getByTestId("nav")).toHaveTextContent("Staff Access");
    expect(screen.getByText("orders page")).toBeInTheDocument();
  });

  it("an ordinary user has no Staff Access entry and the page refuses", () => {
    scope.mockReturnValue({ role: "BIRTHDAY_USER", isAdmin: false, canManageAccess: false, accessAdminOnly: false });
    wrap(<BirthdayShell><AccessPage /></BirthdayShell>);
    expect(screen.getByTestId("nav")).not.toHaveTextContent("Staff Access");
    expect(screen.getByTestId("empty-state")).toHaveTextContent("Access administration required");
    expect(screen.queryByTestId("access-page")).not.toBeInTheDocument();
  });
});
