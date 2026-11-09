import { describe, expect, it } from "vitest";
import { deriveModuleHealth, shouldRetryStatus, statusRetryDelay, summaryPathFor } from "../module-status";

const failed = (error: unknown, signal?: "SCALED_TO_ZERO" | "STARTING") =>
  deriveModuleHealth({ isPending: false, isSuccess: false, error, signal });
const http = (status: number) => Object.assign(new Error("x"), { status });
const timeout = new DOMException("timed out", "TimeoutError");

describe("deriveModuleHealth", () => {
  it("reports a responding service as healthy, even if a replica signal is stale", () =>
    expect(deriveModuleHealth({ isPending: false, isSuccess: true, error: null, signal: "SCALED_TO_ZERO" })).toBe("HEALTHY"));
  it("shows idle only on a confirmed scale-to-zero signal", () => expect(failed(timeout, "SCALED_TO_ZERO")).toBe("IDLE"));
  it("shows starting only on startup evidence", () => expect(failed(timeout, "STARTING")).toBe("STARTING"));
  it("keeps checking during a slow response or retries", () =>
    expect(deriveModuleHealth({ isPending: true, isSuccess: false, error: timeout })).toBe("CHECKING"));
  it("does not claim idle or an outage on a timeout", () => expect(failed(timeout)).toBe("UNKNOWN"));
  it("does not claim idle or an outage on a network failure", () => expect(failed(new TypeError("fetch"))).toBe("UNKNOWN"));
  it.each([500, 502, 503, 504])("treats %i after retries as unavailable", (s) => expect(failed(http(s))).toBe("UNAVAILABLE"));
  it.each([401, 403, 404])("does not treat %i as an outage", (s) => expect(failed(http(s))).toBe("UNKNOWN"));
});

describe("retry policy", () => {
  it("retries a bounded number of times with backoff", () => {
    expect([0, 1, 2].map((n) => shouldRetryStatus(n, timeout))).toEqual([true, true, false]);
    expect(shouldRetryStatus(0, http(503))).toBe(true);
    expect([statusRetryDelay(0), statusRetryDelay(1)]).toEqual([5000, 15000]);
  });
  it.each([401, 403, 404])("never retries %i", (s) => expect(shouldRetryStatus(0, http(s))).toBe(false));
});

describe("summaryPathFor", () => {
  it("gives a future module the standard path with no registration", () =>
    expect(summaryPathFor("future-app")).toBe("/api/future-app/summary"));
  it("keeps the established exception", () => expect(summaryPathFor("talent-flow")).toBe("/api/talent/summary"));
});
