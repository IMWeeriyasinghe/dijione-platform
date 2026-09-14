import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

// AppShell's real dependency tree pulls in TanStack Query, the real
// SupplierAuthProvider (sessionStorage-backed), and LoginScreen's own
// form. This test is scoped to the Shell component's own gating logic —
// no token -> LoginScreen, a token -> the portal chrome + sign-out — so
// both are replaced with light stand-ins, same pattern as
// apps/talent-web's talent-shell.test.tsx. next/link is mocked too:
// Next's App Router Link requires a router context this unit test never
// mounts.
vi.mock("next/link", () => ({
  default: ({ href, children, ...rest }: { href: string; children: ReactNode }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));

vi.mock("@/lib/supplier-auth", () => ({
  useSupplierAuth: vi.fn(),
  SupplierAuthProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

vi.mock("@/lib/portal-me", () => ({ usePortalMe: vi.fn() }));

vi.mock("../login-screen", () => ({
  LoginScreen: () => <div data-testid="login-screen">Sign in to the supplier portal</div>,
}));

import { useSupplierAuth } from "@/lib/supplier-auth";
import { usePortalMe } from "@/lib/portal-me";
import { AppShell } from "../app-shell";

const mockedUseSupplierAuth = vi.mocked(useSupplierAuth);
const mockedUsePortalMe = vi.mocked(usePortalMe);

describe("AppShell (supplier portal)", () => {
  it("renders the login screen when no supplier token is present", () => {
    mockedUseSupplierAuth.mockReturnValue({ token: null, setToken: vi.fn(), ready: true });

    render(<AppShell>content</AppShell>);

    expect(screen.getByTestId("login-screen")).toBeInTheDocument();
    expect(screen.queryByText("Dashboard")).not.toBeInTheDocument();
  });

  it("renders the portal chrome and content once a supplier token is present", () => {
    mockedUseSupplierAuth.mockReturnValue({ token: "tok-123", setToken: vi.fn(), ready: true });

    render(<AppShell>portal content</AppShell>);

    expect(screen.queryByTestId("login-screen")).not.toBeInTheDocument();
    expect(screen.getByText("Dashboard")).toBeInTheDocument();
    expect(screen.getByText("Orders")).toBeInTheDocument();
    expect(screen.getByText("portal content")).toBeInTheDocument();
  });

  it("shows a read-only preview banner during impersonation (§C)", () => {
    mockedUseSupplierAuth.mockReturnValue({ token: "tok-123", setToken: vi.fn(), ready: true });
    mockedUsePortalMe.mockReturnValue({
      supplier_name: "Acme Bakery",
      user_name: "Jane Baker",
      read_only: true,
    });

    render(<AppShell>portal content</AppShell>);

    expect(screen.getByText(/read-only internal preview/i)).toBeInTheDocument();
    expect(screen.getByText(/Jane Baker/)).toBeInTheDocument();
  });

  it("shows no banner for a normal (non-read-only) session", () => {
    mockedUseSupplierAuth.mockReturnValue({ token: "tok-123", setToken: vi.fn(), ready: true });
    mockedUsePortalMe.mockReturnValue({
      supplier_name: "Acme Bakery",
      user_name: "Jane Baker",
      read_only: false,
    });

    render(<AppShell>portal content</AppShell>);

    expect(screen.queryByText(/read-only internal preview/i)).not.toBeInTheDocument();
  });

  it("renders the official Dijital Team logo in the header (§18 branding)", () => {
    mockedUseSupplierAuth.mockReturnValue({ token: "tok-123", setToken: vi.fn(), ready: true });

    render(<AppShell>content</AppShell>);

    const logo = screen.getByAltText("Dijital Team") as HTMLImageElement;
    expect(logo).toBeInTheDocument();
    expect(logo.getAttribute("src")).toBe("/brand/dijital-team-logo.png");
  });

  it("clears the token when Sign out is clicked", async () => {
    const setToken = vi.fn();
    mockedUseSupplierAuth.mockReturnValue({ token: "tok-123", setToken, ready: true });
    const user = userEvent.setup();

    render(<AppShell>content</AppShell>);
    await user.click(screen.getByRole("button", { name: /sign out/i }));

    expect(setToken).toHaveBeenCalledWith(null);
  });
});
