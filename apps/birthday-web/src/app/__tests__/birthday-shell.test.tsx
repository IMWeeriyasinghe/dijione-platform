import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/lib/api", () => ({
  getReleaseMetadata: vi.fn().mockResolvedValue({ release_date: null }),
}));

// BirthdayShell's real dependency tree pulls in the design system's full
// AppShell chrome, each with its own API calls. This test is scoped to
// birthday-shell.tsx's own logic — gate on useBirthdayScope(), which nav
// items render — so the design-system shell is replaced with a light
// stand-in rather than deep rendered, same pattern as apps/talent-web's
// talent-shell.test.tsx.
vi.mock("@dijione/auth-client", () => ({
  useBirthdayScope: vi.fn(),
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
  VersionFooter: ({ appName }: { appName: string }) => <p data-testid="version-footer">{appName}</p>,
}));

import { useBirthdayScope } from "@dijione/auth-client";
import { BirthdayShell } from "../birthday-shell";

const mockedUseBirthdayScope = vi.mocked(useBirthdayScope);

function wrap(ui: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

describe("BirthdayShell", () => {
  it("shows a no-access empty state for a persona with no DijiBirthday role", () => {
    mockedUseBirthdayScope.mockReturnValue(null);

    wrap(<BirthdayShell>content</BirthdayShell>);

    expect(screen.getByTestId("empty-state")).toHaveTextContent("No DijiBirthday access");
    expect(screen.queryByTestId("top-nav-title")).not.toBeInTheDocument();
  });

  it("renders the full DijiBirthday nav for a persona holding a birthday role", () => {
    mockedUseBirthdayScope.mockReturnValue({ role: "BIRTHDAY_ADMIN", isAdmin: true });

    wrap(<BirthdayShell>content</BirthdayShell>);

    expect(screen.getByTestId("top-nav-title")).toHaveTextContent("Birthday Workflow Automation");
    expect(screen.getByText("Upcoming Birthdays")).toBeInTheDocument();
    expect(screen.getByText("Cake Orders")).toBeInTheDocument();
    expect(screen.getByText("Suppliers")).toBeInTheDocument();
    expect(screen.queryByTestId("empty-state")).not.toBeInTheDocument();
  });
});
