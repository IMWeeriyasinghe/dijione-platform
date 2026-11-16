import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";

// Adding an employee before their first sign-in: directory search first, manual entry as the fallback.
const push = vi.hoisted(() => vi.fn());
vi.mock("next/navigation", () => ({ useRouter: () => ({ push, refresh: vi.fn() }) }));

const api = vi.hoisted(() => ({
  listAdminUsers: vi.fn(), listAdminModules: vi.fn(), createAdminUser: vi.fn(), searchDirectory: vi.fn(),
  addUserFromDirectory: vi.fn(),
}));
vi.mock("@/lib/api", async (orig) => ({ ...(await orig<typeof import("@/lib/api")>()), ...api }));

import { ApiError } from "@/lib/api";
import Page from "../users/page";

const ANA = {
  entra_object_id: "00000001-0000-4000-8000-000000000000", full_name: "Ana Perera", email: "ana@example.com",
  user_principal_name: "ana@example.com", job_title: "Engineer", department: "Engineering", employee_number: "0107",
  employee_record: "MATCHED", existing_user_id: null,
};
const SVC = { ...ANA, entra_object_id: "00000002-0000-4000-8000-000000000000", full_name: "Backup Service",
  email: "svc@example.com", employee_number: null, employee_record: "NOT_FOUND", job_title: null };
const BEN = { ...ANA, entra_object_id: "00000003-0000-4000-8000-000000000000", full_name: "Ben", email: "ben@example.com",
  existing_user_id: 12 };

function open() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><Page /></QueryClientProvider>);
  fireEvent.click(screen.getByRole("button", { name: /add user/i }));
}

function search(term: string) {
  fireEvent.change(screen.getByLabelText(/search the directory/i), { target: { value: term } });
}

beforeEach(() => {
  push.mockReset();
  Object.values(api).forEach((f) => f.mockReset());
  api.listAdminUsers.mockResolvedValue([]);
  api.listAdminModules.mockResolvedValue([]);
  api.searchDirectory.mockResolvedValue([ANA, SVC, BEN]);
});

describe("Users -> Add User from the directory", () => {
  it("searches as the administrator types and shows the directory and HR facts", async () => {
    open();
    search("an");
    await waitFor(() => expect(api.searchDirectory).toHaveBeenCalledWith("an"));
    const results = await screen.findAllByTestId("directory-result");
    expect(results).toHaveLength(3);
    expect(results[0]).toHaveTextContent("Ana Perera");
    expect(results[0]).toHaveTextContent("Engineer · Engineering · Employee No. 0107");
    expect(results[0]).toHaveTextContent("In BambooHR");
    expect(results[1]).toHaveTextContent("Not in BambooHR");
    expect(results[2]).toHaveTextContent(/already in dijione/i);
    expect(screen.getByRole("link", { name: /open profile/i })).toHaveAttribute("href", "/users/12");
  });

  it("does not search for a single character", async () => {
    open();
    search("a");
    await new Promise((r) => setTimeout(r, 400));
    expect(api.searchDirectory).not.toHaveBeenCalled();
  });

  it("adds the selected person by directory identity and opens the new profile", async () => {
    api.addUserFromDirectory.mockResolvedValue({ id: 91 });
    open();
    search("ana");
    fireEvent.click((await screen.findAllByRole("button", { name: /^select$/i }))[0]);
    const selection = screen.getByTestId("directory-selection");
    expect(selection).toHaveTextContent("Ana Perera");
    expect(selection).toHaveTextContent("Engineering");
    expect(selection).toHaveTextContent("0107");
    fireEvent.click(screen.getAllByRole("button", { name: /add user/i }).at(-1) as HTMLButtonElement);
    await waitFor(() => expect(api.addUserFromDirectory).toHaveBeenCalledWith(ANA.entra_object_id));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/users/91"));
    expect(api.createAdminUser).not.toHaveBeenCalled();
  });

  it("explains that an unmatched account gets no employee access", async () => {
    open();
    search("backup");
    fireEvent.click((await screen.findAllByRole("button", { name: /^select$/i }))[1]);
    expect(screen.getByText(/default employee access and view as stay off/i)).toBeInTheDocument();
  });

  it("offers the existing profile when the server reports a duplicate", async () => {
    api.addUserFromDirectory.mockRejectedValue(new ApiError(409, "This person already has a DijiOne profile.", { existing_user_id: 7 }));
    open();
    search("ana");
    fireEvent.click((await screen.findAllByRole("button", { name: /^select$/i }))[0]);
    fireEvent.click(screen.getAllByRole("button", { name: /add user/i }).at(-1) as HTMLButtonElement);
    expect(await screen.findByText(/already has a DijiOne profile/i)).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: /open profile/i }).at(-1)).toHaveAttribute("href", "/users/7");
    expect(push).not.toHaveBeenCalled();
  });
});

describe("Users -> Add User manually (fallback)", () => {
  function manual() {
    open();
    fireEvent.click(screen.getByRole("button", { name: /enter manually/i }));
    return screen.getAllByRole("button", { name: /add user/i }).at(-1) as HTMLButtonElement;
  }

  it("submits the trimmed details and marks the profile as awaiting verification", async () => {
    api.createAdminUser.mockResolvedValue({ id: 91 });
    const submit = manual();
    expect(screen.getByText(/awaiting directory verification/i)).toBeInTheDocument();
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
    const submit = manual();
    fireEvent.change(screen.getByLabelText(/work email/i), { target: { value: "taken@example.com" } });
    fireEvent.change(screen.getByLabelText(/full name/i), { target: { value: "Taken" } });
    fireEvent.click(submit);
    expect(await screen.findByText(/already exists/)).toBeInTheDocument();
    expect(push).not.toHaveBeenCalled();
  });
});
