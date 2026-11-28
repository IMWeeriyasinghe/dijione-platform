import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { PERM, type AtworkScope } from "@/lib/atwork-scope";

const scopeMock = vi.hoisted(() => ({ value: {} as { loading: boolean; failed: boolean; scope: AtworkScope | null } }));
vi.mock("@/lib/atwork-scope", async (orig) => {
  const actual = await orig<typeof import("@/lib/atwork-scope")>();
  return { ...actual, useAtworkScope: () => ({ ...scopeMock.value, retry: vi.fn() }) };
});
vi.mock("@/lib/hooks", () => ({
  useDisplay: () => ({ zone: "Asia/Colombo", format: "24h" }),
  useOnline: () => true,
}));

const mgmt = vi.hoisted(() => ({
  report: vi.fn(),
  reportSessions: vi.fn(),
  missed: vi.fn(),
  correctionReport: vi.fn(),
  corrections: vi.fn(),
  download: vi.fn(),
}));
vi.mock("@/lib/api", async (orig) => {
  const actual = await orig<typeof import("@/lib/api")>();
  return { ...actual, management: mgmt };
});

import ReportsPage from "@/app/management/reports/page";

const MANAGER: AtworkScope = {
  role: "ATWORK_MANAGER",
  permissions: [PERM.ACCESS, PERM.MANAGEMENT, PERM.REPORTS, PERM.EXPORT],
};

const SUMMARY = {
  date_from: "2026-11-01", date_to: "2026-11-28", time_zone: "Asia/Colombo",
  session_count: 10,
  totals: { gross_seconds: 72000, break_seconds: 3600, net_seconds: 68400, provisional_seconds: 0 },
  by_work_mode: [{ work_mode: "OFFICE", gross_seconds: 36000, break_seconds: 1800, net_seconds: 34200, provisional_seconds: 0 }],
  by_day: [{ date: "2026-11-01", gross_seconds: 7200, break_seconds: 600, net_seconds: 6600, provisional_seconds: 0 }],
  employee_total: 2, limit: 25, offset: 0,
  by_employee: [
    { platform_user_id: 1, employee_name: "Alice Smith", session_count: 5, totals: { gross_seconds: 36000, break_seconds: 1800, net_seconds: 34200, provisional_seconds: 0 } },
    { platform_user_id: 2, employee_name: "Bob Jones", session_count: 5, totals: { gross_seconds: 36000, break_seconds: 1800, net_seconds: 34200, provisional_seconds: 0 } },
  ],
  chart_employees: [
    { platform_user_id: 1, employee_name: "Alice Smith", session_count: 5, totals: { gross_seconds: 36000, break_seconds: 1800, net_seconds: 34200, provisional_seconds: 0 } },
  ],
};

const MISSED = {
  threshold_hours: 10, total: 1,
  items: [{ session_id: "s1", platform_user_id: 3, employee_name: "Carol Lee", work_mode: "OFFICE", check_in_at: "2026-11-27T08:00:00+00:00", open_seconds: 50000, break_open: false }],
};

const CORRECTIONS = { total: 2, by_status: { PENDING: 2 } };
const CORRECTIONS_LIST = {
  total: 1, limit: 25, offset: 0,
  items: [{ id: "c1", platform_user_id: 1, employee_name: "Alice Smith", kind: "AMEND", status: "PENDING", session_id: "s1", reason: "Wrong time", original: null, proposed: { work_mode: "OFFICE", check_in_at: "2026-11-01T09:00:00", check_out_at: "2026-11-01T17:00:00", breaks: [], status: "OPEN" }, reviewer_name: null, reviewed_at: null, decision_note: null, created_at: "2026-11-27T10:00:00+00:00", updated_at: "2026-11-27T10:00:00+00:00", can_decide: true }],
};

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}><ReportsPage /></QueryClientProvider>);
}

beforeEach(() => {
  scopeMock.value = { loading: false, failed: false, scope: MANAGER };
  mgmt.report.mockResolvedValue(SUMMARY);
  mgmt.reportSessions.mockResolvedValue({ date_from: "2026-11-01", date_to: "2026-11-28", time_zone: "Asia/Colombo", total: 0, limit: 25, offset: 0, by_status: {}, by_mode: {}, items: [] });
  mgmt.missed.mockResolvedValue(MISSED);
  mgmt.correctionReport.mockResolvedValue(CORRECTIONS);
  mgmt.corrections.mockResolvedValue(CORRECTIONS_LIST);
});

describe("ReportsPage", () => {
  it("requires management + reports permissions", () => {
    scopeMock.value = { loading: false, failed: false, scope: { role: "ATWORK_USER", permissions: [PERM.ACCESS] } };
    renderPage();
    expect(screen.getByText("Report access required")).toBeInTheDocument();
  });

  it("renders four report tabs", () => {
    renderPage();
    expect(screen.getByRole("tab", { name: "Employee Summary" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Sessions" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Missed Check-outs" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Corrections" })).toBeInTheDocument();
  });

  it("shows employee data in the default summary tab", async () => {
    renderPage();
    await waitFor(() => expect(screen.getByText("Alice Smith")).toBeInTheDocument());
    expect(screen.getByText("Bob Jones")).toBeInTheDocument();
  });

  it("switches to Sessions tab and calls reportSessions", async () => {
    renderPage();
    fireEvent.click(screen.getByRole("tab", { name: "Sessions" }));
    await waitFor(() => expect(mgmt.reportSessions).toHaveBeenCalled());
  });

  it("switches to Missed Check-outs tab and shows overdue sessions", async () => {
    renderPage();
    fireEvent.click(screen.getByRole("tab", { name: "Missed Check-outs" }));
    await waitFor(() => expect(screen.getByText("Carol Lee")).toBeInTheDocument());
  });

  it("switches to Corrections tab and shows correction rows", async () => {
    renderPage();
    fireEvent.click(screen.getByRole("tab", { name: "Corrections" }));
    await waitFor(() => expect(screen.getByText("Alice Smith")).toBeInTheDocument());
  });

  it("shows CSV and Excel download buttons with export permission", async () => {
    renderPage();
    await waitFor(() => expect(screen.getByText("Alice Smith")).toBeInTheDocument());
    expect(screen.getByRole("button", { name: /download csv/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /download excel/i })).toBeInTheDocument();
  });

  it("hides download buttons without export permission", () => {
    scopeMock.value = { loading: false, failed: false, scope: { role: "ATWORK_MANAGER", permissions: [PERM.ACCESS, PERM.MANAGEMENT, PERM.REPORTS] } };
    renderPage();
    expect(screen.queryByRole("button", { name: /download csv/i })).not.toBeInTheDocument();
  });

  it("expands employee detail panel on row click", async () => {
    renderPage();
    await waitFor(() => expect(screen.getByText("Alice Smith")).toBeInTheDocument());
    fireEvent.click(screen.getByText("Alice Smith"));
    expect(screen.getByText(/View full attendance history/)).toBeInTheDocument();
  });
});
