import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

// AdminShell's real dependency tree pulls in the design system's full
// AppShell chrome (Sidebar/TopNav/NotificationsPanel/UserMenu, each with
// their own API calls). This test is scoped to admin-shell.tsx's own
// logic — gate on usePlatformAdmin(), which nav sections render — so the
// design-system shell is replaced with a light stand-in rather than deep
// rendered, same pattern as apps/talent-web's talent-shell.test.tsx.
vi.mock("@dijione/auth-client", () => ({
  usePlatformAdmin: vi.fn(),
}));

vi.mock("@dijione/design-system", () => ({
  AuthGate: ({ children }: { children: ReactNode }) => <>{children}</>,
  EmptyState: ({ title, description }: { title: string; description: string }) => (
    <div data-testid="empty-state">
      <p>{title}</p>
      <p>{description}</p>
    </div>
  ),
  AppShell: ({
    topNavTitle,
    sections,
    footer,
    children,
  }: {
    topNavTitle?: string;
    sections: { items: { label: string; href: string }[] }[];
    footer?: ReactNode;
    children: ReactNode;
  }) => (
    <div>
      <h1 data-testid="top-nav-title">{topNavTitle}</h1>
      <nav data-testid="nav-items">
        {sections.flatMap((section) => section.items).map((item) => (
          <span key={item.href}>{item.label}</span>
        ))}
      </nav>
      <div data-testid="footer">{footer}</div>
      <main>{children}</main>
    </div>
  ),
}));

import { usePlatformAdmin } from "@dijione/auth-client";
import { AdminShell } from "../admin-shell";

const mockedUsePlatformAdmin = vi.mocked(usePlatformAdmin);

describe("AdminShell", () => {
  it("shows an access-required empty state for a non-admin persona", () => {
    mockedUsePlatformAdmin.mockReturnValue(false);

    render(<AdminShell>content</AdminShell>);

    expect(screen.getByTestId("empty-state")).toHaveTextContent("Administration access required");
    expect(screen.queryByTestId("top-nav-title")).not.toBeInTheDocument();
  });

  it("renders the full Admin Center nav for a SUPER_ADMIN/PLATFORM_ADMIN persona", () => {
    mockedUsePlatformAdmin.mockReturnValue(true);

    render(<AdminShell>content</AdminShell>);

    expect(screen.getByTestId("top-nav-title")).toHaveTextContent("DijiOne Admin");
    expect(screen.getByText("Users")).toBeInTheDocument();
    expect(screen.getByText("Roles")).toBeInTheDocument();
    expect(screen.getByText("Client Access")).toBeInTheDocument();
    expect(screen.getByText("Audit")).toBeInTheDocument();
    // The gated empty state must not leak into the authorized render.
    expect(screen.queryByTestId("empty-state")).not.toBeInTheDocument();
  });
});
