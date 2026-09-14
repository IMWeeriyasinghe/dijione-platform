import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

// Phase 1.6 §15 (R14) — Cake Orders gets whole-row click (the one table
// that didn't have it) and a Days-Until-Birthday display column.

const searchParamsValue = vi.hoisted(() => ({ current: new URLSearchParams() }));
vi.mock("next/navigation", () => ({
  useSearchParams: () => searchParamsValue.current,
  useRouter: () => ({ push: pushMock }),
}));

const pushMock = vi.fn();

vi.mock("next/link", () => ({
  default: ({ href, children, onClick }: any) => (
    <a href={href} onClick={onClick}>{children}</a>
  ),
}));

vi.mock("@dijione/contracts", () => ({
  ORDER_STATUSES: ["PENDING_VERIFICATION", "SENT_TO_SUPPLIER", "COMPLETED"],
  LEAD_TIME_CLASSES: ["NORMAL"],
  ADDRESS_VERIFICATION_STATUSES: ["NOT_CHECKED"],
}));

vi.mock("@dijione/design-system", () => {
  const P = ({ children }: { children: ReactNode }) => <div>{children}</div>;
  return {
    EmptyState: () => <p>empty</p>,
    ErrorState: () => <p>error</p>,
    FormField: ({ children }: any) => <div>{children}</div>,
    Input: (props: any) => <input {...props} />,
    LoadingState: () => <p>loading</p>,
    Pagination: () => <div>pagination</div>,
    PageHeader: ({ title }: any) => <h1>{title}</h1>,
    SearchInput: (props: any) => <input {...props} />,
    Select: ({ children, ...props }: any) => <select {...props}>{children}</select>,
    SortableTh: ({ label }: any) => <th>{label}</th>,
    StatusBadge: ({ status }: any) => <span>{status}</span>,
    Table: P,
    Td: ({ children, ...rest }: any) => <td {...rest}>{children}</td>,
    Thead: P,
    Tr: ({ children, ...rest }: any) => <tr {...rest}>{children}</tr>,
    useSortToggle: () => vi.fn(),
  };
});

const { listOrders } = vi.hoisted(() => ({ listOrders: vi.fn() }));
vi.mock("@/lib/api", () => ({ listOrders }));

import OrdersPage from "../orders/page";

function wrap(ui: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

const today = new Date();
const iso = (d: Date) => d.toISOString().slice(0, 10);

describe("Cake Orders page (§15/R14)", () => {
  beforeEach(() => {
    pushMock.mockClear();
    searchParamsValue.current = new URLSearchParams();
    listOrders.mockResolvedValue({
      items: [
        {
          id: 7, order_reference: "BDAY-EMP7-2026-00001", employee_id: "7", employee_number: "7",
          employee_name: "Jane Doe", birthday_date: iso(today), birthday_year: today.getFullYear(),
          office_location: "Colombo", lead_time_class: "NORMAL", status: "PENDING_VERIFICATION",
          supplier_id: null, supplier_name: null, delivery_date: null, catalogue_item_id: null,
          requires_admin_review: false, exception_reason: null, verify_by: null,
          address_verification_status: "NOT_CHECKED",
        },
      ],
      total: 1, page: 1, page_size: 20,
    });
  });

  it("clicking anywhere on a row navigates to the order", async () => {
    wrap(<OrdersPage />);
    const row = (await screen.findByText("Jane Doe")).closest("tr")!;
    row.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    expect(pushMock).toHaveBeenCalledWith("/orders/7");
  });

  it("shows 'Today' in the Days Until column for a birthday_date of today", async () => {
    wrap(<OrdersPage />);
    expect(await screen.findByText("Today")).toBeInTheDocument();
  });

  it("shows '—' for a terminal order regardless of birthday_date", async () => {
    listOrders.mockResolvedValue({
      items: [
        {
          id: 8, order_reference: "BDAY-EMP8-2026-00001", employee_id: "8", employee_number: "8",
          employee_name: "Terminal Person", birthday_date: iso(today), birthday_year: today.getFullYear(),
          office_location: "Colombo", lead_time_class: "NORMAL", status: "COMPLETED",
          supplier_id: null, supplier_name: null, delivery_date: null, catalogue_item_id: null,
          requires_admin_review: false, exception_reason: null, verify_by: null,
          address_verification_status: "NOT_CHECKED",
        },
      ],
      total: 1, page: 1, page_size: 20,
    });
    wrap(<OrdersPage />);
    expect(await screen.findByText("Terminal Person")).toBeInTheDocument();
    // "—" appears at least once (the Days Until cell) even though the
    // order's birthday_date is today — a settled order's countdown is
    // meaningless and must not show "Today"/a day count.
    expect(screen.getAllByText("—").length).toBeGreaterThanOrEqual(1);
  });

  it("initializes the Lead Time Class filter from ?lead_time_class= in the URL (round 3 dashboard deep-link)", async () => {
    searchParamsValue.current = new URLSearchParams("lead_time_class=NORMAL");

    wrap(<OrdersPage />);
    await screen.findByText("Jane Doe");

    const select = document.getElementById("lead-time-filter") as HTMLSelectElement;
    expect(select.value).toBe("NORMAL");
    expect(listOrders).toHaveBeenCalledWith(expect.objectContaining({ lead_time_class: "NORMAL" }));
  });
});
