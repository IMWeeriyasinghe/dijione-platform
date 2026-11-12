import { beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, renderHook, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ApiError } from "@dijione/auth-client";
import TodayPage from "@/app/page";
import { groupByDay } from "@/components/history";
import { attendance, AtworkError, errorMessage, type Session, type Status, type Today } from "@/lib/api";
import { addDays, duration, localDate, localInputToUtc, rangeError, utcToLocalInput } from "@/lib/format";
import { useAttendanceAction } from "@/lib/hooks";
import { PERM, type AtworkScope } from "@/lib/atwork-scope";

// Isolated component tests only: the running application always uses the real API.
const scopeMock = vi.hoisted(() => ({ value: { loading: false, failed: false, scope: null as AtworkScope | null, retry: () => {} } }));
vi.mock("@/lib/atwork-scope", async (orig) => ({ ...(await orig<typeof import("@/lib/atwork-scope")>()), useAtworkScope: () => scopeMock.value }));

const totals = { gross_seconds: 3600, break_seconds: 600, net_seconds: 3000 };
const session = (over: Partial<Session> = {}): Session => ({
  id: "s1", work_mode: "REMOTE", status: "OPEN", check_in_at: "2026-11-09T03:00:00Z", check_out_at: null, time_zone: "Asia/Colombo",
  origin: "RECORDED", correction_count: 0, breaks: [], totals, ...over,
});
const today = (sessions: Session[] = []): Today => ({ date: "2026-11-09", time_zone: "Asia/Colombo", server_time: "2026-11-09T04:00:00Z", session_count: sessions.length, totals, sessions });
const status = (over: Partial<Status>): Status => ({ state: "NOT_CHECKED_IN", server_time: "2026-11-09T04:00:00Z", time_zone: "Asia/Colombo", session: null, ...over });
const wrapper = ({ children }: { children: React.ReactNode }) => <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>{children}</QueryClientProvider>;
const policy = { enabled_work_modes: ["OFFICE", "REMOTE"], business_time_zone: "Asia/Colombo", missed_checkout_hours: 12, time_format: "24h", default_history_days: 30, server_time: "2026-11-09T04:00:00Z" } as const;

function mock(s: Status, t: Today = today()) {
  vi.spyOn(attendance, "status").mockResolvedValue(s);
  vi.spyOn(attendance, "today").mockResolvedValue(t);
  vi.spyOn(attendance, "policy").mockResolvedValue({ ...policy, enabled_work_modes: [...policy.enabled_work_modes] });
}
const allPerms = { role: "R", permissions: [PERM.READ_OWN, PERM.RECORD_OWN] };

beforeEach(() => { vi.restoreAllMocks(); scopeMock.value.scope = allPerms; });

describe("Today", () => {
  it("offers only enabled work modes and check-in when not checked in", async () => {
    mock(status({}));
    render(<TodayPage />, { wrapper });
    expect(await screen.findByRole("button", { name: "Check In" })).toBeEnabled();
    expect(screen.getByLabelText("Office")).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByLabelText("Client Site")).not.toBeInTheDocument());
  });
  it("shows break and check-out while working", async () => {
    mock(status({ state: "WORKING", session: session() }), today([session()]));
    render(<TodayPage />, { wrapper });
    expect(await screen.findByRole("button", { name: "Start Break" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Check Out" })).toBeInTheDocument();
  });
  it("offers no check-out during a break", async () => {
    const s = session({ breaks: [{ id: "b", started_at: "2026-11-09T03:50:00Z", ended_at: null }] });
    mock(status({ state: "ON_BREAK", session: s }), today([s]));
    render(<TodayPage />, { wrapper });
    expect(await screen.findByRole("button", { name: "End Break" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Check Out" })).not.toBeInTheDocument();
  });
  it("gives read-only employees no actions", async () => {
    scopeMock.value.scope = { role: "R", permissions: [PERM.READ_OWN] };
    mock(status({}));
    render(<TodayPage />, { wrapper });
    expect(await screen.findByText(/cannot record it/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Check In" })).not.toBeInTheDocument();
  });
  it("hides attendance without the read permission", () => {
    scopeMock.value.scope = { role: "R", permissions: [] };
    render(<TodayPage />, { wrapper });
    expect(screen.getByText("Attendance access required")).toBeInTheDocument();
  });
  it("never shows success before the server confirms", async () => {
    mock(status({}));
    let finish: (v: never) => void = () => {};
    vi.spyOn(attendance, "checkIn").mockReturnValue(new Promise((r) => { finish = r as never; }));
    render(<TodayPage />, { wrapper });
    fireEvent.click(await screen.findByRole("button", { name: "Check In" }));
    await waitFor(() => expect(attendance.checkIn).toHaveBeenCalledOnce());
    expect(screen.queryByText("You are checked in.")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Check In" }));
    expect(attendance.checkIn).toHaveBeenCalledOnce();
    await act(async () => finish({ state: "WORKING" } as never));
    expect(await screen.findByText("You are checked in.")).toBeInTheDocument();
  });
});

describe("date rollover", () => {
  it("refetches the summary when the local day changes", async () => {
    mock(status({ server_time: "2026-11-09T18:31:00Z" }), today());
    render(<TodayPage />, { wrapper });
    await waitFor(() => expect(vi.mocked(attendance.today).mock.calls.length).toBeGreaterThan(1));
  });
});

describe("request IDs", () => {
  const ok = { replayed: false } as never;
  it("reuses the ID after an uncertain failure", async () => {
    const spy = vi.spyOn(attendance, "startBreak").mockRejectedValueOnce(new TypeError("network")).mockResolvedValueOnce(ok);
    const { result } = renderHook(() => useAttendanceAction(), { wrapper });
    act(() => result.current.run({ kind: "BREAK_START" }));
    await waitFor(() => expect(result.current.retryable).not.toBeNull());
    act(() => result.current.retry());
    await waitFor(() => expect(spy).toHaveBeenCalledTimes(2));
    expect(spy.mock.calls[0][0]).toBe(spy.mock.calls[1][0]);
  });
  it("does not reuse the ID once the status shows the action resolved", async () => {
    const spy = vi.spyOn(attendance, "startBreak").mockRejectedValueOnce(new TypeError("network")).mockResolvedValue(ok);
    const { result, rerender } = renderHook(({ s }) => useAttendanceAction(s), { wrapper, initialProps: { s: "WORKING" } });
    act(() => result.current.run({ kind: "BREAK_START" }));
    await waitFor(() => expect(result.current.retryable).not.toBeNull());
    rerender({ s: "ON_BREAK" });
    expect(result.current.retryable).toBeNull();
    rerender({ s: "WORKING" });
    act(() => result.current.run({ kind: "BREAK_START" }));
    await waitFor(() => expect(spy).toHaveBeenCalledTimes(2));
  });
  it("uses a new ID after a definitive rejection and for each new action", async () => {
    const spy = vi.spyOn(attendance, "startBreak").mockRejectedValueOnce(new AtworkError(409, "x", "BREAK_ALREADY_ACTIVE")).mockResolvedValue(ok);
    const { result } = renderHook(() => useAttendanceAction(), { wrapper });
    act(() => result.current.run({ kind: "BREAK_START" }));
    await waitFor(() => expect(result.current.notice?.tone).toBe("error"));
    expect(result.current.retryable).toBeNull();
    act(() => result.current.run({ kind: "BREAK_START" }));
    await waitFor(() => expect(spy).toHaveBeenCalledTimes(2));
    expect(spy.mock.calls[0][0]).not.toBe(spy.mock.calls[1][0]);
  });
});

describe("helpers", () => {
  it("maps errors", () => {
    expect(errorMessage(new AtworkError(409, "raw", "BREAK_STILL_OPEN"))).toBe("End your break before checking out.");
    expect(errorMessage(new ApiError(401, "x"))).toMatch(/sign in/);
    expect(errorMessage(new ApiError(403, "Missing required permission: a"))).toMatch(/permission/);
    expect(errorMessage(new TypeError("f"))).toMatch(/connection/);
  });
  it("formats and converts business time", () => {
    expect(duration(3661)).toBe("01:01:01");
    expect(localDate("2026-11-09T18:30:00Z", "Asia/Colombo")).toBe("2026-11-10");
    expect(localInputToUtc("2026-11-10T00:00:00", "Asia/Colombo")).toBe("2026-11-09T18:30:00Z");
    expect(utcToLocalInput("2026-11-09T18:30:00Z", "Asia/Colombo")).toBe("2026-11-10T00:00:00");
    expect(localInputToUtc("2026-07-01T12:00:00", "America/New_York")).toBe("2026-07-01T16:00:00Z");
    expect(addDays("2026-12-31", 1)).toBe("2027-01-01");
  });
  it("validates ranges", () => {
    expect(rangeError("2026-11-02", "2026-11-01")).toMatch(/after/);
    expect(rangeError("2025-01-01", "2026-11-01")).toMatch(/366/);
    expect(rangeError("2026-11-01", "2026-11-02")).toBeNull();
  });
  it("places an overnight session under both local days", () => {
    const s = session({ check_in_at: "2026-11-09T18:00:00Z", check_out_at: "2026-11-09T20:00:00Z", status: "COMPLETED" });
    const days = [{ date: "2026-11-09", ...totals }, { date: "2026-11-10", ...totals }];
    expect(groupByDay([s], days, "Asia/Colombo", "2026-11-10T00:00:00Z").map((g) => g.sessions.length)).toEqual([1, 1]);
  });
});
