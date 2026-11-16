import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";

// D4: an administrator can add an employee who has never signed in.
const push = vi.hoisted(() => vi.fn());
vi.mock("next/navigation", () => ({ useRouter: () => ({ push, refresh: vi.fn() }) }));

const api = vi.hoisted(() => ({ listAdminUsers: vi.fn(), listAdminModules: vi.fn(), createAdminUser: vi.fn() }));
vi.mock("@/lib/api", async (orig) => ({ ...(await orig<typeof import("@/lib/api")>()), ...api }));

import { ApiError } from "@/lib/api";
import Page from "../users/page";

function open() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><Page /></QueryClientProvider>);
  fireEvent.click(screen.getByRole("button", { name: /add user/i }));
  return screen.getAllByRole("button", { name: /add user/i }).at(-1) as HTMLButtonElement;
}

beforeEach(() => {
  push.mockReset();
  Object.values(api).forEach((f) => f.mockReset());
  api.listAdminUsers.mockResolvedValue([]);
  api.listAdminModules.mockResolvedValue([]);
});

describe("Users -> Add User", () => {
  it("submits the trimmed details and opens the new user", async () => {
    api.createAdminUser.mockResolvedValue({ id: 91 });
    const submit = open();
    expect(submit).toBeDisabled();
    fireEvent.change(screen.getByLabelText(/work email/i), { target: { value: " new.hire@example.com " } });
    fireEvent.change(screen.getByLabelText(/full name/i), { target: { value: "New Hire" } });
    expect(submit).toBeEnabled();
    fireEvent.click(submit);
    await waitFor(() =>
      expect(api.createAdminUser).toHaveBeenCalledWith({ email: "new.hire@example.com", full_name: "New Hire", title: undefined }),
    );
    await waitFor(() => expect(push).toHaveBeenCalledWith("/users/91"));
  });

  it("shows the server's reason when the user cannot be added", async () => {
    api.createAdminUser.mockRejectedValue(new ApiError(409, "A user with the email taken@example.com already exists."));
    const submit = open();
    fireEvent.change(screen.getByLabelText(/work email/i), { target: { value: "taken@example.com" } });
    fireEvent.change(screen.getByLabelText(/full name/i), { target: { value: "Taken" } });
    fireEvent.click(submit);
    expect(await screen.findByText("A user with the email taken@example.com already exists.")).toBeInTheDocument();
    expect(push).not.toHaveBeenCalled();
  });
});
