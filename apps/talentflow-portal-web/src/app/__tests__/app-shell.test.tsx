import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

// Scoped to the Shell component's own gating logic — no session -> the
// "opened from a secure link" screen; a session -> the workspace chrome +
// sign-out; /access always renders children. next/link and
// next/navigation are mocked (no router mounted in a unit test). Same
// pattern as apps/birthday-supplier-web's app-shell.test.tsx.
vi.mock("next/link", () => ({
  default: ({ href, children, ...rest }: { href: string; children: ReactNode }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));

const pathname = vi.hoisted(() => ({ value: "/" }));
vi.mock("next/navigation", () => ({
  usePathname: () => pathname.value,
}));

vi.mock("@/lib/external-auth", () => ({
  useExternalAuth: vi.fn(),
  ExternalAuthProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

import { useExternalAuth } from "@/lib/external-auth";
import { AppShell } from "../app-shell";

const mockedUseExternalAuth = vi.mocked(useExternalAuth);

// Every staff / internal surface the plan says this app must NEVER show.
const FORBIDDEN_LABELS = [
  "Operations Dashboard",
  "Client Portfolios",
  "All Requests",
  "Candidate Pool",
  "Applications",
  "Interview Manager",
  "Recruitment Postings",
  "Client Access Links",
  "DijiTalentFlow",
];

describe("AppShell (Client Talent Review Workspace)", () => {
  it("shows the secure-link screen when there is no session", () => {
    mockedUseExternalAuth.mockReturnValue({ session: null, establish: vi.fn(), clear: vi.fn() });
    render(<AppShell>content</AppShell>);
    expect(
      screen.getByText(/opened from a secure link/i),
    ).toBeInTheDocument();
    expect(screen.queryByText("Requests")).not.toBeInTheDocument();
    // The official Dijital Team wordmark is on the secure-link screen.
    expect(screen.getByAltText("Dijital Team")).toBeInTheDocument();
  });

  it("renders the workspace chrome with a session and no staff surfaces", () => {
    mockedUseExternalAuth.mockReturnValue({
      session: "sess-1",
      establish: vi.fn(),
      clear: vi.fn(),
    });
    render(<AppShell>workspace content</AppShell>);

    expect(screen.getByText("Client Talent Review Workspace")).toBeInTheDocument();
    expect(screen.getByAltText("Dijital Team")).toBeInTheDocument();
    expect(screen.getByText("Overview")).toBeInTheDocument();
    expect(screen.getByText("Requests")).toBeInTheDocument();
    expect(screen.getByText("Interviews")).toBeInTheDocument();
    expect(screen.getByText("workspace content")).toBeInTheDocument();

    for (const label of FORBIDDEN_LABELS) {
      expect(screen.queryByText(label)).not.toBeInTheDocument();
    }
  });

  it("renders /access children even without a session", () => {
    pathname.value = "/access";
    mockedUseExternalAuth.mockReturnValue({ session: null, establish: vi.fn(), clear: vi.fn() });
    render(
      <AppShell>
        <div data-testid="access-content">redeeming</div>
      </AppShell>,
    );
    expect(screen.getByTestId("access-content")).toBeInTheDocument();
    expect(screen.queryByText(/opened from a secure link/i)).not.toBeInTheDocument();
    pathname.value = "/";
  });

  it("clears the session when Sign out is clicked", async () => {
    const clear = vi.fn();
    mockedUseExternalAuth.mockReturnValue({ session: "sess-1", establish: vi.fn(), clear });
    const user = userEvent.setup();
    render(<AppShell>content</AppShell>);
    await user.click(screen.getByRole("button", { name: /sign out/i }));
    expect(clear).toHaveBeenCalled();
  });
});
