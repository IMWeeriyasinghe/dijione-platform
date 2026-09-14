import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Activity } from "lucide-react";
import { MetricCard } from "@dijione/design-system";

// Round 4 — MetricCard had no min-w-0/wrap guard on its label/value pair,
// unlike DetailRow (OrderDetail.tsx) and the Upcoming Birthdays list rows,
// which both explicitly handle long text. These are STRUCTURAL assertions
// only — jsdom cannot prove real overflow geometry. Actual "does a long
// label/value avoid pushing the document wider" behavior is proven by the
// real-Chromium Puppeteer audit (scripts/verify-birthday-responsive.js) at
// the Dashboard route, never by this unit test.

describe("MetricCard (round 4 — long-content protection)", () => {
  it("text column is min-w-0 so it can shrink inside a flex row instead of forcing overflow", () => {
    render(<MetricCard label="Label" value="42" icon={Activity} />);

    const label = screen.getByText("Label");
    const textColumn = label.parentElement!;
    expect(textColumn.className).toContain("min-w-0");
  });

  it("label and value both carry a wrap class so long content wraps instead of overflowing", () => {
    render(
      <MetricCard
        label="A very long metric label that could otherwise force this card wider than its grid column"
        value="1,234,567"
        icon={Activity}
      />
    );

    const label = screen.getByText(/A very long metric label/);
    const value = screen.getByText("1,234,567");
    expect(label.className).toContain("wrap-break-word");
    expect(value.className).toContain("wrap-break-word");
  });

  it("the icon badge stays a fixed, non-shrinking size regardless of text length", () => {
    render(<MetricCard label="X" value="Y" icon={Activity} />);

    const icon = document.querySelector("svg")!;
    const badge = icon.parentElement!;
    expect(badge.className).toContain("shrink-0");
    expect(badge.className).toContain("size-9");
  });

  it("existing semantics (label text, value text, href click-through) remain unchanged", () => {
    render(<MetricCard label="Orders" value={7} icon={Activity} href="/orders" />);

    expect(screen.getByText("Orders")).toBeInTheDocument();
    expect(screen.getByText("7")).toBeInTheDocument();
    const link = screen.getByRole("link");
    expect(link).toHaveAttribute("href", "/orders");
  });
});
