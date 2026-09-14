import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

// Round 4 — Suppliers list ported to the same FIELDS/card responsive
// pattern as Cake Orders and Upcoming Birthdays: a table on wide
// viewports, adaptive cards below the measured breakpoint, one canonical
// field list so a label/value can never drift between the two renderers.

const pushMock = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: pushMock }) }));

vi.mock("next/link", () => ({
  default: ({ href, children }: any) => <a href={href}>{children}</a>,
}));

vi.mock("@dijione/auth-client", () => ({ useBirthdayScope: () => ({ isAdmin: true }) }));

vi.mock("@dijione/design-system", () => {
  const P = ({ children }: { children: ReactNode }) => <div>{children}</div>;
  return {
    Button: ({ children, ...props }: any) => <button {...props}>{children}</button>,
    EmptyState: () => <p>empty</p>,
    ErrorState: () => <p>error</p>,
    FormField: ({ children }: any) => <div>{children}</div>,
    Input: (props: any) => <input {...props} />,
    LoadingState: () => <p>loading</p>,
    Modal: ({ open, children, title }: any) => (open ? <div role="dialog" aria-label={title}>{children}</div> : null),
    Pagination: () => <div>pagination</div>,
    PageHeader: ({ title, action }: any) => (
      <div>
        <h1>{title}</h1>
        {action}
      </div>
    ),
    SearchInput: (props: any) => <input {...props} />,
    Select: ({ children, ...props }: any) => <select {...props}>{children}</select>,
    SortableTh: ({ label }: any) => <th>{label}</th>,
    StatusBadge: ({ status }: any) => <span>{status}</span>,
    Table: P,
    Td: ({ children, ...rest }: any) => <td {...rest}>{children}</td>,
    Textarea: (props: any) => <textarea {...props} />,
    Th: ({ children }: any) => <th>{children}</th>,
    Thead: P,
    Tr: ({ children, ...rest }: any) => <tr {...rest}>{children}</tr>,
    useSortToggle: (
      _sortBy: string | null,
      _sortDirection: string,
      setSortBy: (v: string) => void
    ) => (key: string) => setSortBy(key),
  };
});

const { listSuppliers, createSupplier } = vi.hoisted(() => ({
  listSuppliers: vi.fn(),
  createSupplier: vi.fn(),
}));
vi.mock("@/lib/api", () => ({ listSuppliers, createSupplier }));

import SuppliersPage from "../suppliers/page";

function wrap(ui: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

describe("Suppliers page (round 4 — FIELDS/card responsive split)", () => {
  beforeEach(() => {
    pushMock.mockClear();
    listSuppliers.mockResolvedValue({
      items: [
        {
          id: 3,
          name: "Sweet Treats Bakery",
          status: "ACTIVE",
          lead_time_days: 2,
          working_days: "Mon-Fri",
          cutoff_time: "14:00",
          escalation_contact_name: "Nimal Perera",
          escalation_contact_email: "nimal@example.com",
        },
      ],
      total: 1,
      page: 1,
      page_size: 20,
    });
  });

  it("renders all 6 operational fields in the table", async () => {
    wrap(<SuppliersPage />);
    await screen.findAllByText("Sweet Treats Bakery");

    expect(screen.getAllByText("ACTIVE").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("2 days").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("Mon-Fri").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("14:00").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("Nimal Perera").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("nimal@example.com").length).toBeGreaterThanOrEqual(1);
  });

  it("card view renders the same data via the same FIELDS as a navigable link", async () => {
    wrap(<SuppliersPage />);
    const matches = await screen.findAllByText("Sweet Treats Bakery");
    // One of the two renders (table row text, card link text) must be
    // inside a real <a href="/suppliers/3">, proving the card is a
    // semantic Link, not a clickable div.
    const cardLink = matches.map((el) => el.closest("a")).find(Boolean);
    expect(cardLink).toHaveAttribute("href", "/suppliers/3");
  });

  it("clicking a table row navigates to the supplier (table click-through unregressed)", async () => {
    wrap(<SuppliersPage />);
    const matches = await screen.findAllByText("Sweet Treats Bakery");
    const row = matches.map((el) => el.closest("tr")).find(Boolean)!;
    row.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    expect(pushMock).toHaveBeenCalledWith("/suppliers/3");
  });

  it("filters by status and re-queries with page reset to 1", async () => {
    wrap(<SuppliersPage />);
    await screen.findAllByText("Sweet Treats Bakery");

    const selects = screen.getAllByRole("combobox");
    const statusSelect = selects.find((s) => s.querySelector('option[value="ACTIVE"]')) as HTMLSelectElement;
    statusSelect.value = "ACTIVE";
    statusSelect.dispatchEvent(new Event("change", { bubbles: true }));

    expect(listSuppliers).toHaveBeenCalledWith(expect.objectContaining({ status_filter: "ACTIVE", page: 1 }));
  });
});
