import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

// ModuleCard's real dependency tree pulls in the design system's Card
// (fine, lightweight) and issues a live runtime-status fetch via
// useAuth/request from @dijione/auth-client. This test is scoped to
// ModuleCard's own navigation/badge logic — a COMING_SOON module renders
// as a static div (never a real navigation target), an ACTIVE module
// renders as a real <a href> (CR §39: next/link would silently strand the
// user across zones, only a full navigation is correct here) — so `request`
// is mocked to a pending promise (no real fetch, no need to await/settle
// the runtime-status badge for what this test asserts).
vi.mock("@dijione/auth-client", () => ({
  useAuth: vi.fn(),
  request: vi.fn(() => new Promise(() => {})),
}));

import { useAuth } from "@dijione/auth-client";
import { ModuleCard } from "../ModuleCard";

const mockedUseAuth = vi.mocked(useAuth);

function renderWithQueryClient(children: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{children}</QueryClientProvider>);
}

describe("ModuleCard", () => {
  it("renders a COMING_SOON module as a static element, not a navigation link, with no role badge", () => {
    mockedUseAuth.mockReturnValue({ user: { module_roles: [] } } as never);

    const { container } = renderWithQueryClient(
      <ModuleCard
        module={{
          id: 3, key: "spark", name: "DijiSpark", description: "HR / Spark Hire Workflows",
          icon: "Sparkles", route: "/spark", status: "COMING_SOON", enabled: true, display_order: 3,
        }}
      />
    );

    expect(container.querySelector("a")).not.toBeInTheDocument();
    expect(screen.getByText("Coming soon")).toBeInTheDocument();
    expect(screen.queryByText(/Your role:/)).not.toBeInTheDocument();
  });

  it("renders an ACTIVE module as a real <a href> anchor with a role badge when the persona holds a role in it", () => {
    mockedUseAuth.mockReturnValue({
      user: { module_roles: [{ module_key: "talent-flow", role: "TA_MEMBER", client_id: null, enabled: true }] },
    } as never);

    renderWithQueryClient(
      <ModuleCard
        module={{
          id: 1, key: "talent-flow", name: "DijiTalentFlow", description: "Talent Operations",
          icon: "Users", route: "/talent-flow", status: "ACTIVE", enabled: true, display_order: 1,
        }}
      />
    );

    const link = screen.getByRole("link");
    expect(link).toHaveAttribute("href", "/talent-flow");
    expect(screen.getByText(/Your role:/)).toBeInTheDocument();
    expect(screen.queryByText("Coming soon")).not.toBeInTheDocument();
  });

  it("does not show a role badge for an ACTIVE module the persona holds no role in", () => {
    mockedUseAuth.mockReturnValue({ user: { module_roles: [] } } as never);

    renderWithQueryClient(
      <ModuleCard
        module={{
          id: 2, key: "birthday", name: "DijiBirthday", description: "Birthday Workflow Automation",
          icon: "Cake", route: "/birthday", status: "ACTIVE", enabled: true, display_order: 2,
        }}
      />
    );

    expect(screen.queryByText(/Your role:/)).not.toBeInTheDocument();
  });
});
