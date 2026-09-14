import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

// Phase 1.5 §D — every internal dashboard tile is clickable, and each
// Upcoming Birthdays row navigates to its order.

vi.mock("next/link", () => ({
  default: ({ href, children }: { href: string; children: ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

vi.mock("@dijione/design-system", () => {
  const P = ({ children }: { children: ReactNode }) => <div>{children}</div>;
  return {
    Card: P, CardContent: P, CardHeader: P, CardTitle: P,
    ErrorState: () => <p>error</p>,
    LoadingState: () => <p>loading</p>,
    PageHeader: ({ title }: any) => <h1>{title}</h1>,
    StatusBadge: ({ status }: any) => <span>{status}</span>,
    MetricCard: ({ label, value }: any) => (
      <div>
        <span>{label}</span>
        <span>{value}</span>
      </div>
    ),
  };
});

const { getDashboardSummary, getUpcoming } = vi.hoisted(() => ({
  getDashboardSummary: vi.fn(),
  getUpcoming: vi.fn(),
}));
vi.mock("@/lib/api", () => ({ getDashboardSummary, getUpcoming }));

import DashboardPage from "../page";

function wrap(ui: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

const linkFor = (label: string) =>
  screen.getByText(label).closest("a") as HTMLAnchorElement;

describe("DashboardPage tiles (§D)", () => {
  beforeEach(() => {
    getDashboardSummary.mockResolvedValue({
      pending_verification_count: 1,
      verification_overdue_count: 2,
      requires_review_count: 0,
      exceptions_count: 0,
      acceptance_awaiting_count: 0,
      acceptance_overdue_count: 0,
      on_hold_count: 0,
      deliveries_today_at_risk_count: 3,
      overdue_delivery_count: 4,
      open_issues_count: 0,
      unmatched_emails_count: 0,
      upcoming_count: 5,
      by_status: {},
      by_lead_time_class: {},
      detection_health: { healthy: true, last_scan_at: null, last_status: "OK", consecutive_deferrals: 0, stale: false },
    });
    getUpcoming.mockResolvedValue({
      orders: [
        { id: 42, employee_name: "Jane Doe", birthday_date: "2026-09-20", status: "PENDING_VERIFICATION" },
      ],
    });
  });

  it("links the three formerly-static tiles to their filtered views", async () => {
    wrap(<DashboardPage />);
    expect(await screen.findByText("Deliveries today at risk")).toBeInTheDocument();

    expect(linkFor("Deliveries today at risk")).toHaveAttribute("href", "/orders?due=today");
    expect(linkFor("Overdue deliveries")).toHaveAttribute("href", "/orders?due=overdue");
    expect(linkFor("Upcoming (14 days)")).toHaveAttribute("href", "/upcoming");
  });

  it("links the split Open Issues / Unmatched Supplier Email tiles separately (§5)", async () => {
    wrap(<DashboardPage />);
    expect(await screen.findByText("Open issues")).toBeInTheDocument();
    expect(linkFor("Open issues")).toHaveAttribute("href", "/orders?has_open_issue=true");
    expect(linkFor("Unmatched supplier email")).toHaveAttribute("href", "/inbound-emails");
  });

  it("links Awaiting/Overdue supplier acceptance with exact semantic params (§6)", async () => {
    wrap(<DashboardPage />);
    expect(await screen.findByText("Awaiting supplier acceptance")).toBeInTheDocument();
    expect(linkFor("Awaiting supplier acceptance")).toHaveAttribute("href", "/orders?acceptance=awaiting");
    expect(linkFor("Acceptance overdue")).toHaveAttribute("href", "/orders?acceptance=overdue");
  });

  it("makes each Upcoming Birthdays row a link to the order", async () => {
    wrap(<DashboardPage />);
    const row = (await screen.findByText(/Jane Doe/)).closest("a") as HTMLAnchorElement;
    expect(row).toHaveAttribute("href", "/orders/42");
    expect(within(row).getByText("PENDING_VERIFICATION")).toBeInTheDocument();
  });
});
