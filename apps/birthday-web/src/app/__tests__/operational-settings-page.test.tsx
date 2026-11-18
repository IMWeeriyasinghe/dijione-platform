import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { MockButtonProps, MockErrorProps, MockFieldProps, MockHeadingProps, MockInputProps, MockModalProps } from "@/test-support/mock-props";

let isAdmin = true;
vi.mock("@dijione/auth-client", () => ({
  useBirthdayScope: () => ({ isAdmin }),
  ApiError: class ApiError extends Error {},
}));

vi.mock("@dijione/design-system", () => ({
  Button: ({ children, loading, ...props }: MockButtonProps) => (
    <button {...props} data-loading={loading ? "true" : "false"}>
      {children}
    </button>
  ),
  EmptyState: ({ title }: MockHeadingProps) => <div data-testid="empty-state">{title}</div>,
  ErrorState: ({ onRetry }: MockErrorProps) => <button onClick={onRetry}>retry</button>,
  FormField: ({ label, children }: MockFieldProps) => (
    <label>
      {label}
      {children}
    </label>
  ),
  Input: (props: MockInputProps) => <input {...props} />,
  LoadingState: () => <p>loading</p>,
  Modal: ({ open, children, title }: MockModalProps) =>
    open ? (
      <div role="dialog" aria-label={title}>
        {children}
      </div>
    ) : null,
  PageHeader: ({ title }: MockHeadingProps) => <h1>{title}</h1>,
}));

const { getConfig, updateConfig, getCleanStartPreview, applyCleanStart } = vi.hoisted(() => ({
  getConfig: vi.fn(),
  updateConfig: vi.fn(),
  getCleanStartPreview: vi.fn(),
  applyCleanStart: vi.fn(),
}));
vi.mock("@/lib/api", () => ({ getConfig, updateConfig, getCleanStartPreview, applyCleanStart }));

import OperationalSettingsPage from "../admin/settings/page";

function wrap(ui: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

const today = new Date().toISOString().slice(0, 10);
const plus7 = new Date(Date.now() + 7 * 86_400_000).toISOString().slice(0, 10);

function config(overrides = {}) {
  return {
    id: 1, normal_threshold_days: 10, short_notice_threshold_days: 5, urgent_threshold_days: 2,
    window_lookback_days: 1, window_lookahead_days: 14, default_quantity: 1, verify_buffer_days: 2,
    acknowledgement_sla_hours: 24, auto_release_enabled: true,
    operational_start_date: null, supplier_lead_time_days: 7, first_eligible_birthday: null,
    clean_start_applied_at: null, clean_start_applied_by: null, clean_start_excluded_count: null,
    clean_start_first_eligible: null, updated_by: null,
    ...overrides,
  };
}

const PREVIEW = {
  operational_start_date: today, supplier_lead_time_days: 7, first_eligible_birthday: plus7,
  total: 59, by_status: { PENDING_VERIFICATION: 45, REQUIRES_ATTENTION: 7, ON_HOLD: 6, SENT_TO_SUPPLIER: 1 },
  released_to_supplier: 1, already_applied: false, clean_start_applied_at: null, clean_start_excluded_count: null,
};

beforeEach(() => {
  isAdmin = true;
  vi.clearAllMocks();
});

describe("Operational Settings page", () => {
  it("computes the first eligible birthday as start + lead time (25 Nov + 7 = 2 Dec)", async () => {
    getConfig.mockResolvedValue(config());
    getCleanStartPreview.mockResolvedValue({ ...PREVIEW, first_eligible_birthday: null, total: 0, by_status: {}, released_to_supplier: 0 });
    wrap(<OperationalSettingsPage />);
    const date = await screen.findByLabelText(/Operational Start Date/);
    const start = new Date(Date.now() + 7 * 86_400_000);
    const iso = start.toISOString().slice(0, 10);
    await userEvent.type(date, iso);
    const expected = new Date(start.getTime() + 7 * 86_400_000).toISOString().slice(0, 10);
    expect(screen.getByTestId("first-eligible")).toHaveTextContent(`First eligible birthday: ${expected}`);
  });

  it("saving settings calls PATCH only, never the clean start", async () => {
    getConfig.mockResolvedValue(config());
    getCleanStartPreview.mockResolvedValue({ ...PREVIEW, first_eligible_birthday: null, total: 0, by_status: {}, released_to_supplier: 0 });
    updateConfig.mockResolvedValue(config({ operational_start_date: today, first_eligible_birthday: plus7 }));
    wrap(<OperationalSettingsPage />);
    await userEvent.type(await screen.findByLabelText(/Operational Start Date/), today);
    await userEvent.click(screen.getByRole("button", { name: "Save settings" }));
    await waitFor(() =>
      expect(updateConfig).toHaveBeenCalledWith({ operational_start_date: today, supplier_lead_time_days: 7 }),
    );
    expect(applyCleanStart).not.toHaveBeenCalled();
  });

  it("previews the impact before confirming, then applies once with the previewed boundary", async () => {
    getConfig.mockResolvedValue(config({ operational_start_date: today, first_eligible_birthday: plus7 }));
    getCleanStartPreview.mockResolvedValue(PREVIEW);
    applyCleanStart.mockResolvedValue({ ...PREVIEW, already_applied: true });
    wrap(<OperationalSettingsPage />);

    const preview = await screen.findByTestId("clean-start-preview");
    expect(preview).toHaveTextContent("59 orders will be excluded");
    expect(preview).toHaveTextContent("Pending verification: 45");
    expect(preview).toHaveTextContent("Sent to supplier: 1");
    expect(screen.getByTestId("released-warning")).toHaveTextContent("1 of these was already sent to the supplier");
    expect(preview).toHaveTextContent("No supplier cancellation email is sent");
    expect(preview).toHaveTextContent("full history");

    await userEvent.click(screen.getByRole("button", { name: "Apply clean start…" }));
    const dialog = screen.getByRole("dialog", { name: "Establish the operational baseline" });
    expect(dialog).toHaveTextContent(`First eligible birthday: ${plus7}`);
    expect(applyCleanStart).not.toHaveBeenCalled();
    await userEvent.click(within(dialog).getByRole("button", { name: "Confirm clean start" }));
    await waitFor(() => expect(applyCleanStart).toHaveBeenCalledWith(plus7));
  });

  it("shows the applied record and no apply button once the clean start is done", async () => {
    getConfig.mockResolvedValue(
      config({
        operational_start_date: today, first_eligible_birthday: plus7,
        clean_start_applied_at: `${today}T10:00:00Z`, clean_start_excluded_count: 59, clean_start_first_eligible: plus7,
      }),
    );
    getCleanStartPreview.mockResolvedValue({ ...PREVIEW, total: 0, by_status: {}, already_applied: true });
    wrap(<OperationalSettingsPage />);
    expect(await screen.findByTestId("clean-start-applied")).toHaveTextContent("59 pre-launch orders were excluded");
    expect(screen.queryByRole("button", { name: "Apply clean start…" })).toBeNull();
  });

  it("is admin-only", async () => {
    isAdmin = false;
    wrap(<OperationalSettingsPage />);
    expect(await screen.findByTestId("empty-state")).toHaveTextContent("Admin access required");
    expect(getConfig).not.toHaveBeenCalled();
  });
});
