import { describe, expect, it } from "vitest";
import { formatSyncAbsolute, formatSyncTooltip, parseSyncInstant, relativeSyncTime } from "../syncTime";

describe("parseSyncInstant", () => {
  it("parses offset-bearing ISO (PostgreSQL)", () => {
    expect(parseSyncInstant("2026-11-13T11:00:00+00:00")?.toISOString()).toBe("2026-11-13T11:00:00.000Z");
    expect(parseSyncInstant("2026-11-13T16:30:00+05:30")?.toISOString()).toBe("2026-11-13T11:00:00.000Z");
    expect(parseSyncInstant("2026-11-13T11:00:00Z")?.toISOString()).toBe("2026-11-13T11:00:00.000Z");
  });

  it("treats a timezone-naive value as the backend's UTC, not browser-local", () => {
    expect(parseSyncInstant("2026-11-13T11:00:00.123456")?.toISOString()).toBe("2026-11-13T11:00:00.123Z");
  });

  it("returns null for missing or invalid input — never invents a date", () => {
    expect(parseSyncInstant(null)).toBeNull();
    expect(parseSyncInstant(undefined)).toBeNull();
    expect(parseSyncInstant("")).toBeNull();
    expect(parseSyncInstant("not-a-date")).toBeNull();
  });
});

describe("formatSyncAbsolute / formatSyncTooltip", () => {
  const instant = new Date("2026-11-13T11:00:00Z");

  it('formats as "13 Nov 2026, 4:30 PM" in the viewer\'s zone', () => {
    expect(formatSyncAbsolute(instant, "Asia/Colombo")).toBe("13 Nov 2026, 4:30 PM");
  });

  it("converts across zones, including the date boundary", () => {
    expect(formatSyncAbsolute(instant, "UTC")).toBe("13 Nov 2026, 11:00 AM");
    expect(formatSyncAbsolute(new Date("2026-11-13T22:15:00Z"), "Asia/Colombo")).toBe("14 Nov 2026, 3:45 AM");
    expect(formatSyncAbsolute(instant, "America/New_York")).toBe("13 Nov 2026, 6:00 AM");
  });

  it("names the timezone in the tooltip", () => {
    const t = formatSyncTooltip(instant, "Asia/Colombo");
    expect(t).toContain("Last successful Lever sync:");
    expect(t).toContain("13 November 2026");
    expect(t).toContain("(Asia/Colombo)");
    expect(t).toMatch(/GMT\+5:30|IST/);
  });
});

describe("relativeSyncTime", () => {
  const now = new Date("2026-11-13T14:00:00Z").getTime();
  it("keeps the relative wording", () => {
    expect(relativeSyncTime(null, now)).toBe("never");
    expect(relativeSyncTime(new Date(now - 20_000), now)).toBe("just now");
    expect(relativeSyncTime(new Date(now - 25 * 60_000), now)).toBe("25 min ago");
    expect(relativeSyncTime(new Date(now - 3 * 3_600_000), now)).toBe("3 hrs ago");
    expect(relativeSyncTime(new Date(now - 26 * 3_600_000), now)).toBe("1 day ago");
  });
});
