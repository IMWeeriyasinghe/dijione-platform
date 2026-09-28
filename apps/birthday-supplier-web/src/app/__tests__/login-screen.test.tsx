import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

// LoginScreen picks its UI from /api/birthday/supplier/auth/config. Mock
// the api module + supplier-auth context it touches.
const getSupplierAuthConfig = vi.fn();
const listDevSupplierPersonas = vi.fn();

vi.mock("@/lib/api", () => ({
  getSupplierAuthConfig: () => getSupplierAuthConfig(),
  listDevSupplierPersonas: () => listDevSupplierPersonas(),
  devSupplierLogin: vi.fn(),
}));

vi.mock("@/lib/supplier-auth", () => ({
  useSupplierAuth: () => ({ token: null, setToken: vi.fn(), ready: true }),
}));

let mockPathname = "/";
vi.mock("next/navigation", () => ({
  usePathname: () => mockPathname,
}));

import { LoginScreen } from "../login-screen";

function renderScreen(node: ReactNode = <LoginScreen />) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{node}</QueryClientProvider>);
}

describe("Supplier LoginScreen — auth-mode aware", () => {
  beforeEach(() => {
    getSupplierAuthConfig.mockReset();
    listDevSupplierPersonas.mockReset();
    listDevSupplierPersonas.mockResolvedValue([]);
    mockPathname = "/";
  });

  it("shows 'Sign in with Microsoft' and no dev wording when supplier_auth_mode is entra", async () => {
    getSupplierAuthConfig.mockResolvedValue({ supplier_auth_mode: "entra" });
    renderScreen();

    const link = await screen.findByRole("link", { name: /sign in with microsoft/i });
    expect(link).toHaveAttribute("href", "/login");
    expect(screen.queryByText(/development mode/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/pick a supplier persona/i)).not.toBeInTheDocument();
    expect(listDevSupplierPersonas).not.toHaveBeenCalled();
  });

  it("carries the current path as return_to when landed on a deep link while signed out", async () => {
    mockPathname = "/orders/42";
    getSupplierAuthConfig.mockResolvedValue({ supplier_auth_mode: "entra" });
    renderScreen();

    const link = await screen.findByRole("link", { name: /sign in with microsoft/i });
    expect(link).toHaveAttribute("href", "/login?return_to=%2Forders%2F42");
  });

  it("omits return_to when already on the portal home", async () => {
    mockPathname = "/";
    getSupplierAuthConfig.mockResolvedValue({ supplier_auth_mode: "entra" });
    renderScreen();

    const link = await screen.findByRole("link", { name: /sign in with microsoft/i });
    expect(link).toHaveAttribute("href", "/login");
  });

  it("shows the persona picker when supplier_auth_mode is dev", async () => {
    getSupplierAuthConfig.mockResolvedValue({ supplier_auth_mode: "dev" });
    renderScreen();

    expect(await screen.findByText(/pick a supplier persona/i)).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /sign in with microsoft/i })).not.toBeInTheDocument();
  });

  it("falls back to the persona picker if the config call fails", async () => {
    getSupplierAuthConfig.mockRejectedValue(new Error("network"));
    renderScreen();

    expect(await screen.findByText(/pick a supplier persona/i)).toBeInTheDocument();
  });
});
