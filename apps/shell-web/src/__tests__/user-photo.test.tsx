import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

// The signed-in employee's avatar uses their Microsoft 365 photo, served by platform-api
// (/api/auth/me/photo); without one it keeps the initials.
const state = vi.hoisted(() => ({ photo: null as string | null, requested: [] as (string | null)[] }));
vi.mock("@dijione/auth-client", async (orig) => ({
  ...(await orig<typeof import("@dijione/auth-client")>()),
  useAuth: () => ({
    user: { id: 1, full_name: "Ana Perera", email: "ana@example.com", title: "Engineer", avatar_color: null },
    logout: vi.fn(),
  }),
  useAuthorizedImage: (path: string | null) => {
    state.requested.push(path);
    return state.photo;
  },
}));

import { UserMenu } from "@dijione/design-system";

beforeEach(() => {
  state.photo = null;
  state.requested = [];
});

describe("Signed-in avatar", () => {
  it("shows the person's photo from DijiOne's own endpoint", () => {
    state.photo = "blob:me";
    render(<UserMenu />);
    expect(screen.getByTestId("avatar-photo")).toHaveAttribute("src", "blob:me");
    expect(state.requested).toContain("/api/auth/me/photo");
  });

  it("keeps the initials when there is no photo", () => {
    render(<UserMenu />);
    expect(screen.queryByTestId("avatar-photo")).not.toBeInTheDocument();
    expect(screen.getByTestId("avatar-initials")).toHaveTextContent("AP");
  });
});
