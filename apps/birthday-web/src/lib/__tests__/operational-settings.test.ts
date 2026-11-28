import { describe, expect, it } from "vitest";
import { addDaysIso, validateLeadTime, validateOrderCreationWindow, validateStartDate } from "../operational-settings";

describe("operational settings validation", () => {
  const now = new Date("2026-11-18T12:00:00Z");

  it("adds the lead time to the start date", () => {
    expect(addDaysIso("2026-11-25", 7)).toBe("2026-12-02");
    expect(addDaysIso("2027-02-25", 7)).toBe("2027-03-04");
  });

  it("validates the start date relative to today, not a fixed year", () => {
    expect(validateStartDate("2026-11-25", now)).toBeNull();
    expect(validateStartDate("", now)).toBeNull();
    expect(validateStartDate("2026-02-30", now)).toMatch(/valid date/);
    expect(validateStartDate("2028-01-01", now)).toMatch(/365 days/);
    expect(validateStartDate("2027-11-01", new Date("2027-10-01T00:00:00Z"))).toBeNull();
  });

  it("rejects negative, fractional and excessive lead times", () => {
    expect(validateLeadTime("7")).toBeNull();
    expect(validateLeadTime("0")).toBeNull();
    expect(validateLeadTime("-1")).not.toBeNull();
    expect(validateLeadTime("2.5")).not.toBeNull();
    expect(validateLeadTime("61")).not.toBeNull();
  });

  it("validates the order creation window (1–90, integers only)", () => {
    expect(validateOrderCreationWindow("14")).toBeNull();
    expect(validateOrderCreationWindow("1")).toBeNull();
    expect(validateOrderCreationWindow("90")).toBeNull();
    expect(validateOrderCreationWindow("0")).not.toBeNull();
    expect(validateOrderCreationWindow("-1")).not.toBeNull();
    expect(validateOrderCreationWindow("91")).not.toBeNull();
    expect(validateOrderCreationWindow("2.5")).not.toBeNull();
    expect(validateOrderCreationWindow("")).not.toBeNull();
  });
});
