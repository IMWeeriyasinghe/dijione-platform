import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { CheckoutDialog } from "@/components/checkout-dialog";
import { validateCorrection, type CorrectionDraft } from "@/lib/correction-validation";

const dialog = (over = {}) => {
  const props = { netSeconds: 3661, grossSeconds: 7322, onCancel: vi.fn(), onConfirm: vi.fn(), ...over };
  render(<CheckoutDialog {...props} />);
  return props;
};

describe("check-out confirmation", () => {
  it("shows the session duration and explains the consequences", () => {
    dialog();
    expect(screen.getByRole("dialog", { name: "End this session?" })).toBeInTheDocument();
    expect(screen.getByText("01:01:01")).toBeInTheDocument();
    expect(screen.getByText("02:02:02")).toBeInTheDocument();
    expect(screen.getByText(/you can check in again/)).toBeInTheDocument();
    expect(screen.getByText(/correction request/)).toBeInTheDocument();
  });

  it("checks out only on confirmation", () => {
    const p = dialog();
    expect(screen.getByRole("button", { name: "Keep Working" })).toHaveFocus();
    fireEvent.click(screen.getByRole("button", { name: "Keep Working" }));
    expect(p.onCancel).toHaveBeenCalledOnce();
    expect(p.onConfirm).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Confirm Check Out" }));
    expect(p.onConfirm).toHaveBeenCalledOnce();
  });

  it("closes on Escape", () => {
    const p = dialog();
    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });
    expect(p.onCancel).toHaveBeenCalledOnce();
  });
});

describe("correction form validation", () => {
  const base: CorrectionDraft = { checkIn: "2026-11-09T14:00:00", checkOut: "2026-11-09T17:00:00", breaks: [], isOpen: false, reason: "Accidental", nowLocal: "2026-11-09T18:00:00" };
  const row = (start: string, end: string, key = 1) => ({ key, start: `2026-11-09T${start}:00`, end: `2026-11-09T${end}:00` });

  it("accepts a valid missing session", () => expect(validateCorrection(base)).toBeNull());
  it("rejects future times", () => {
    expect(validateCorrection({ ...base, checkOut: "2026-11-09T19:00:00" })).toMatch(/future/);
    expect(validateCorrection({ ...base, checkIn: "2026-11-09T19:00:00", checkOut: "", isOpen: true })).toMatch(/future/);
  });
  it("rejects reversed sessions and bad breaks", () => {
    expect(validateCorrection({ ...base, checkOut: "2026-11-09T13:00:00" })).toMatch(/before check-in/);
    expect(validateCorrection({ ...base, breaks: [row("15:00", "14:30")] })).toMatch(/end before/);
    expect(validateCorrection({ ...base, breaks: [row("13:00", "14:30")] })).toMatch(/within/);
    expect(validateCorrection({ ...base, breaks: [row("14:10", "15:00"), row("14:30", "15:30", 2)] })).toMatch(/overlap/);
  });
  it("needs a reason", () => expect(validateCorrection({ ...base, reason: "no" })).toMatch(/reason/));
});
