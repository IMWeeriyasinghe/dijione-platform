import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { DayHeading, SessionBadge, SessionDetails, SessionRow, TotalsCards } from "@/components/ui";
import type { Session } from "@/lib/api";

const base: Session = {
  id: "s1", work_mode: "OFFICE", status: "OPEN", check_in_at: "2026-11-10T07:16:19Z", check_out_at: null,
  time_zone: "Asia/Colombo", origin: "RECORDED", correction_count: 0, breaks: [],
  totals: { gross_seconds: 217000, break_seconds: 0, net_seconds: 217000 },
};

describe("unverified attendance", () => {
  it("shows unverified time separately from confirmed totals", () => {
    render(<TotalsCards totals={{ gross_seconds: 0, break_seconds: 0, net_seconds: 0, provisional_seconds: 3 * 3600 }} />);
    expect(screen.getByText(/Unverified time, not included above: 3h/)).toBeInTheDocument();
  });

  it("adds nothing when there is no unverified time", () => {
    render(<TotalsCards totals={{ gross_seconds: 3600, break_seconds: 0, net_seconds: 3600 }} />);
    expect(screen.queryByText(/Unverified/)).not.toBeInTheDocument();
  });

  it("labels an unverified session", () => {
    render(<SessionBadge session={{ ...base, unverified: true }} />);
    expect(screen.getByText("Unverified")).toBeInTheDocument();
  });

  it("does not label a normal session", () => {
    render(<SessionBadge session={base} />);
    expect(screen.queryByText("Unverified")).not.toBeInTheDocument();
  });

  it("shows a day's unverified time next to its confirmed totals", () => {
    render(<DayHeading day="2026-11-11" totals={{ gross_seconds: 0, break_seconds: 0, net_seconds: 0, provisional_seconds: 24 * 3600 }} />);
    expect(screen.getByText(/Unverified 24h/)).toBeInTheDocument();
  });
});

describe("single-session views", () => {
  const unverified: Session = { ...base, unverified: true, elapsed_seconds: 60 * 3600,
    totals: { gross_seconds: 0, break_seconds: 0, net_seconds: 0, provisional_seconds: 60 * 3600 } };

  it("lists an unverified session as elapsed and not counted, never as net", () => {
    render(<SessionRow session={unverified} zone="Asia/Colombo" format="24h" href="/x" />);
    expect(screen.getByText(/Elapsed 60h 00m/)).toBeInTheDocument();
    expect(screen.getByText(/unverified, not counted/)).toBeInTheDocument();
    expect(screen.queryByText(/Net/)).not.toBeInTheDocument();
  });

  it("shows details without a net figure for an unverified session", () => {
    render(<SessionDetails session={unverified} zone="Asia/Colombo" format="24h" />);
    expect(screen.getByText("Elapsed")).toBeInTheDocument();
    expect(screen.getByText("Not counted: unverified")).toBeInTheDocument();
    expect(screen.queryByText("Net")).not.toBeInTheDocument();
  });

  it("keeps gross, break and net for a normal session", () => {
    render(<SessionDetails session={{ ...base, status: "COMPLETED", check_out_at: "2026-11-10T15:16:19Z", totals: { gross_seconds: 8 * 3600, break_seconds: 0, net_seconds: 8 * 3600 } }} zone="Asia/Colombo" format="24h" />);
    expect(screen.getByText("Net")).toBeInTheDocument();
  });
});
