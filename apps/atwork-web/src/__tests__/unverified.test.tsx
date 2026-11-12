import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { DayHeading, SessionBadge, TotalsCards } from "@/components/ui";
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
