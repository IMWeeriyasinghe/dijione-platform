// Human labels for exception reasons that need one; anything else is shown
// as its code, exactly as before.
const LABELS: Record<string, string> = {
  PRE_LAUNCH_EXCLUDED: "Excluded — before operational start",
};

export function exceptionReasonLabel(reason: string): string {
  return LABELS[reason] ?? reason;
}
