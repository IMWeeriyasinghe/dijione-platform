import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

// AuthGate picks the sign-in UI from /api/auth/config's auth_mode. Mock the
// auth-client surface it touches: useAuth (session), getAuthConfig (mode),
// beginEntraLogin (nav), and listDevPersonas (the persona switcher's fetch).
const getAuthConfig = vi.fn();
const beginEntraLogin = vi.fn();

vi.mock("@dijione/auth-client", () => ({
  useAuth: () => ({ user: null, loading: false, login: vi.fn(), logout: vi.fn() }),
  getAuthConfig: () => getAuthConfig(),
  beginEntraLogin: () => beginEntraLogin(),
  listDevPersonas: () => new Promise(() => {}), // pending — persona grid never resolves
}));

import { AuthGate } from "@dijione/design-system";

function renderGate(children: ReactNode = <div>protected</div>) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <AuthGate>{children}</AuthGate>
    </QueryClientProvider>,
  );
}

describe("AuthGate sign-in view selection", () => {
  beforeEach(() => {
    getAuthConfig.mockReset();
    beginEntraLogin.mockReset();
  });

  it("shows the Microsoft sign-in view when auth_mode is entra", async () => {
    getAuthConfig.mockResolvedValue({ auth_mode: "entra" });
    renderGate();
    expect(await screen.findByRole("button", { name: /sign in with microsoft/i })).toBeInTheDocument();
    expect(screen.queryByText(/dev identity mode/i)).not.toBeInTheDocument();
  });

  it("shows the Dev Identity Mode persona switcher when auth_mode is dev", async () => {
    getAuthConfig.mockResolvedValue({ auth_mode: "dev" });
    renderGate();
    expect(await screen.findByText(/dev identity mode/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /sign in with microsoft/i })).not.toBeInTheDocument();
  });

  it("falls back to the persona switcher if the config call fails", async () => {
    getAuthConfig.mockRejectedValue(new Error("network"));
    renderGate();
    await waitFor(() => expect(screen.getByText(/dev identity mode/i)).toBeInTheDocument());
  });
});
