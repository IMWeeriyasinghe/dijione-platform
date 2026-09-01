import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

// TalentShell's real dependency tree pulls in NotificationsPanel/UserMenu
// (their own API calls) and Next's router/image primitives. This test is
// scoped to talent-shell.tsx's own logic — which nav sections, workspace
// title, and footer a persona gets, based on scope.isStaff — so the
// design-system shell and next/link are replaced with light stand-ins
// rather than deep-rendered. AuthGate's own loading/no-user gating is a
// design-system concern with its own test surface, not this file's.
vi.mock("next/link", () => ({
  default: ({ href, children, ...rest }: { href: string; children: ReactNode }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));

vi.mock("@dijione/auth-client", () => ({
  useTalentScope: vi.fn(),
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

import { useTalentScope } from "@dijione/auth-client";
import { TalentShell } from "../talent-shell";

const mockedUseTalentScope = vi.mocked(useTalentScope);

describe("TalentShell", () => {
  it("shows an empty state when the persona holds no DijiTalentFlow role", () => {
    mockedUseTalentScope.mockReturnValue(null);

    render(<TalentShell>content</TalentShell>);

    expect(screen.getByTestId("empty-state")).toHaveTextContent("No DijiTalentFlow access");
  });

  it("renders the staff workspace with staff-only navigation for a staff persona", () => {
    mockedUseTalentScope.mockReturnValue({
      role: "TA_MEMBER",
      clientId: null,
      isStaff: true,
      isClient: false,
      isCustomerSuccessOrManager: false,
    });

    render(<TalentShell>content</TalentShell>);

    expect(screen.getByTestId("top-nav-title")).toHaveTextContent("Talent Acquisition Workspace");
    expect(screen.getByText("Client Portfolios")).toBeInTheDocument();
    expect(screen.getByText("Applications")).toBeInTheDocument();
    expect(screen.getByText("Interview Manager")).toBeInTheDocument();
    expect(screen.getByText("Recruitment Postings")).toBeInTheDocument();
    expect(screen.getByText("Client Access Links")).toBeInTheDocument();
  });

  it("renders the client workspace with only client navigation for a TALENT_CLIENT persona", () => {
    mockedUseTalentScope.mockReturnValue({
      role: "TALENT_CLIENT",
      clientId: 42,
      isStaff: false,
      isClient: true,
      isCustomerSuccessOrManager: false,
    });

    render(<TalentShell>content</TalentShell>);

    expect(screen.getByTestId("top-nav-title")).toHaveTextContent("Client Workspace");
    // Staff-only nav must not leak into the client workspace.
    expect(screen.queryByText("Client Portfolios")).not.toBeInTheDocument();
    expect(screen.queryByText("Applications")).not.toBeInTheDocument();
    expect(screen.queryByText("Recruitment Postings")).not.toBeInTheDocument();
    expect(screen.queryByText("Client Access Links")).not.toBeInTheDocument();
    expect(screen.getByText("My Requests")).toBeInTheDocument();
    // DijiTalentFlow is not a client intake portal (retired 2026-09-01) —
    // no persona sees a "New Talent Request" action anywhere.
    expect(screen.queryByText("New Talent Request")).not.toBeInTheDocument();
  });
});
