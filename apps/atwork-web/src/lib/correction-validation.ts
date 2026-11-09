export type BreakRow = { key: number; start: string; end: string };

export type CorrectionDraft = { checkIn: string; checkOut: string; breaks: BreakRow[]; isOpen: boolean; reason: string; nowLocal: string };

// Mirrors the API's rules for quick feedback. The API remains the authority.
export function validateCorrection({ checkIn, checkOut, breaks, isOpen, reason, nowLocal }: CorrectionDraft): string | null {
  if (!checkIn) return "Enter a check-in time.";
  if (!isOpen && !checkOut) return "Enter a check-out time.";
  if (checkIn > nowLocal) return "Check-in cannot be in the future.";
  if (checkOut && checkOut > nowLocal) return "Check-out cannot be in the future.";
  if (checkOut && checkOut < checkIn) return "Check-out must not be before check-in.";
  for (const b of breaks) {
    if (!b.start || !b.end) return "Enter a start and end for each break.";
    if (b.end < b.start) return "A break must not end before it starts.";
    if (b.start < checkIn || (checkOut && b.end > checkOut)) return "Breaks must fall within the session.";
  }
  const sorted = [...breaks].sort((a, b) => a.start.localeCompare(b.start));
  for (let i = 1; i < sorted.length; i++) if (sorted[i].start < sorted[i - 1].end) return "Breaks must not overlap.";
  if (reason.trim().length < 5) return "Give a reason of at least 5 characters.";
  return null;
}
