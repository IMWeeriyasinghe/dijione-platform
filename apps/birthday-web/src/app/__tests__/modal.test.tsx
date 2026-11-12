import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Modal } from "@dijione/design-system";

// Round 4 — Modal had no height cap / scroll region at all, so a tall form
// (e.g. the Add/Edit Supplier User modal) could push its Cancel/Confirm
// footer buttons off-screen on a short viewport with no way to scroll to
// them. Fixed by making the panel a height-capped (dynamic viewport height,
// not a plain vh unit — vh is unreliable on mobile browsers whose chrome
// collapses/expands) flex column with an internally-scrolling body.
//
// These are STRUCTURAL assertions only (DOM/class contract) — jsdom has no
// real layout engine, so it cannot prove actual scroll/reachability
// behavior. That proof lives in the real-Chromium Puppeteer audit
// (scripts/verify-birthday-responsive.js), never in this unit test.

describe("Modal (round 4 — dvh height cap + scrollable body)", () => {
  it("panel is capped to dynamic viewport height and laid out as a flex column", () => {
    render(
      <Modal open title="Test" onClose={vi.fn()}>
        <p>content</p>
      </Modal>
    );

    const heading = screen.getByRole("heading", { name: "Test" });
    const panel = heading.closest('[class*="max-h-"]')!;
    expect(panel.className).toContain("max-h-[calc(100dvh-2rem)]");
    expect(panel.className).toContain("flex");
    expect(panel.className).toContain("flex-col");
  });

  it("body wrapper is the scroll region, shrinkable and independent of the header", () => {
    render(
      <Modal open title="Test" onClose={vi.fn()}>
        <p data-testid="body-content">content</p>
      </Modal>
    );

    const bodyContent = screen.getByTestId("body-content");
    const bodyWrapper = bodyContent.parentElement!;
    expect(bodyWrapper.className).toContain("min-h-0");
    expect(bodyWrapper.className).toContain("flex-1");
    expect(bodyWrapper.className).toContain("overflow-y-auto");
  });

  it("header (title + close control) renders outside the scrollable body", () => {
    render(
      <Modal open title="Test" onClose={vi.fn()}>
        <p data-testid="body-content">content</p>
      </Modal>
    );

    const heading = screen.getByRole("heading", { name: "Test" });
    const closeButton = screen.getByRole("button", { name: "Close dialog" });
    const bodyWrapper = screen.getByTestId("body-content").parentElement!;

    expect(bodyWrapper.contains(heading)).toBe(false);
    expect(bodyWrapper.contains(closeButton)).toBe(false);
  });

  it("Escape still closes the modal (unregressed by the layout change)", () => {
    const onClose = vi.fn();
    render(
      <Modal open title="Test" onClose={onClose}>
        <p>content</p>
      </Modal>
    );

    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("clicking the overlay still closes the modal (unregressed by the layout change)", () => {
    const onClose = vi.fn();
    render(
      <Modal open title="Test" onClose={onClose}>
        <p>content</p>
      </Modal>
    );

    screen.getByRole("button", { name: "Close" }).click();
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
