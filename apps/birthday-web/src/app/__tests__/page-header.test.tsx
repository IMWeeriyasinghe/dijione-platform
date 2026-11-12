import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { PageHeader } from "@dijione/design-system";

// Round 3 — PageHeader's sm:flex-row (640px) row-share was too early for a
// heavy action (Upcoming Birthdays' 4 selects + a button squeezed the
// description into a narrow column). Fixed with an opt-in actionLayout
// prop rather than changing the default — this pins BOTH halves of that
// promise: the default stays byte-for-byte what every other of the 27
// current PageHeader consumers already relies on, and "stacked" gets the
// corrected structure only when a page explicitly asks for it.

describe("PageHeader actionLayout (round 3)", () => {
  it("defaults to the original 'inline' behavior when actionLayout is omitted", () => {
    render(<PageHeader title="Cake Orders" description="Register of every cake order." action={<button>New</button>} />);

    const heading = screen.getByRole("heading", { name: "Cake Orders" });
    const row = heading.closest("div")!.parentElement!;
    expect(row.className).toContain("sm:flex-row");
    expect(row.className).toContain("sm:items-center");
    expect(row.className).not.toContain("2xl:flex-row");
  });

  it("actionLayout='inline' explicitly renders the same unchanged markup", () => {
    render(<PageHeader title="Users" action={<button>Create</button>} actionLayout="inline" />);

    const heading = screen.getByRole("heading", { name: "Users" });
    const row = heading.closest("div")!.parentElement!;
    expect(row.className).toContain("sm:flex-row");
  });

  it("actionLayout='stacked' renders the corrected 2xl structure instead", () => {
    render(
      <PageHeader
        title="Upcoming Birthdays"
        description="Active team members with birthdays approaching."
        actionLayout="stacked"
        action={<button>Run Detection</button>}
      />
    );

    const heading = screen.getByRole("heading", { name: "Upcoming Birthdays" });
    const row = heading.closest("div")!.parentElement!;
    expect(row.className).toContain("2xl:flex-row");
    expect(row.className).toContain("2xl:flex-wrap");
    expect(row.className).not.toContain("sm:flex-row");
  });

  it("stacked mode's action block is full-width below 2xl (never narrower than the row)", () => {
    render(<PageHeader title="X" actionLayout="stacked" action={<button data-testid="act">Go</button>} />);

    const actionButton = screen.getByTestId("act");
    const actionWrapper = actionButton.parentElement!;
    expect(actionWrapper.className).toContain("w-full");
    expect(actionWrapper.className).toContain("2xl:w-auto");
  });

  it("renders no action wrapper at all when action is omitted, in either layout", () => {
    const { container: inlineContainer } = render(<PageHeader title="No Action" />);
    expect(inlineContainer.querySelectorAll("div").length).toBeLessThanOrEqual(2);

    const { container: stackedContainer } = render(<PageHeader title="No Action" actionLayout="stacked" />);
    expect(stackedContainer.querySelector("button")).not.toBeInTheDocument();
  });
});
