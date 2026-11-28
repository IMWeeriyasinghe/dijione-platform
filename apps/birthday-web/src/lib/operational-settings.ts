// Client-side mirror of the backend validation in
// apps/birthday-api/app/schemas/config.py. Year-independent: the start date
// must be within a year either side of today. The backend is authoritative.

export const OPERATIONAL_START_WINDOW_DAYS = 365;
export const MAX_SUPPLIER_LEAD_TIME_DAYS = 60;
export const MIN_ORDER_CREATION_WINDOW_DAYS = 1;
export const MAX_ORDER_CREATION_WINDOW_DAYS = 90;

const ISO = /^\d{4}-\d{2}-\d{2}$/;

function parseIso(value: string): Date | null {
  if (!ISO.test(value)) return null;
  const [y, m, d] = value.split("-").map(Number);
  const date = new Date(Date.UTC(y, m - 1, d));
  return date.getUTCFullYear() === y && date.getUTCMonth() === m - 1 && date.getUTCDate() === d ? date : null;
}

function todayUtc(now: Date): Date {
  return new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()));
}

export function addDaysIso(value: string, days: number): string | null {
  const date = parseIso(value);
  if (!date) return null;
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

export function validateStartDate(value: string, now: Date = new Date()): string | null {
  if (!value) return null; // empty = no boundary
  const date = parseIso(value);
  if (!date) return "Enter a valid date.";
  const diffDays = Math.round((date.getTime() - todayUtc(now).getTime()) / 86_400_000);
  if (Math.abs(diffDays) > OPERATIONAL_START_WINDOW_DAYS) {
    return `Must be within ${OPERATIONAL_START_WINDOW_DAYS} days of today.`;
  }
  return null;
}

export function validateLeadTime(value: string): string | null {
  if (value.trim() === "" || !/^\d+$/.test(value.trim())) return "Enter a whole number of days.";
  const n = Number(value);
  if (n < 0 || n > MAX_SUPPLIER_LEAD_TIME_DAYS) return `Must be between 0 and ${MAX_SUPPLIER_LEAD_TIME_DAYS}.`;
  return null;
}

export function validateOrderCreationWindow(value: string): string | null {
  if (value.trim() === "" || !/^-?\d+$/.test(value.trim())) return "Enter a whole number of days.";
  const n = Number(value);
  if (!Number.isInteger(n) || n < MIN_ORDER_CREATION_WINDOW_DAYS || n > MAX_ORDER_CREATION_WINDOW_DAYS) {
    return `Must be between ${MIN_ORDER_CREATION_WINDOW_DAYS} and ${MAX_ORDER_CREATION_WINDOW_DAYS}.`;
  }
  return null;
}

export function formatIsoDate(value: string): string {
  const date = parseIso(value);
  if (!date) return value;
  return date.toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" });
}
