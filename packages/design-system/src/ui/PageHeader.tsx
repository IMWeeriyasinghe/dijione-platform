export function PageHeader({
  title,
  description,
  action,
  actionLayout = "inline",
}: {
  title: string;
  description?: string;
  action?: React.ReactNode;
  /** "inline" (default) — the original, unchanged behavior: action shares a
   * row with the title from `sm:` (640px) up. Correct for a single small
   * action (a badge, one button) — confirmed safe for every current
   * consumer except Upcoming Birthdays by direct inspection.
   * "stacked" — title+description always render on their own full-width
   * row; action becomes a full-width row below, only sharing a line with
   * the title at `2xl:` (1536px)+ where there's genuinely enough room. For
   * a page whose action is a heavier control cluster (multiple filters)
   * than a single button/badge — same proven pattern already validated for
   * OrderDetail.tsx's header this session. Opt-in only: this never changes
   * any existing consumer's behavior unless it explicitly asks for it. */
  actionLayout?: "inline" | "stacked";
}) {
  if (actionLayout === "stacked") {
    return (
      <div className="mb-6 flex flex-col gap-4 rounded-2xl 2xl:flex-row 2xl:flex-wrap 2xl:items-start 2xl:justify-between">
        <div className="min-w-0 max-w-full">
          <h1 className="text-2xl font-semibold text-dt-text-primary">{title}</h1>
          {description && <p className="mt-1 max-w-2xl text-sm text-dt-text-secondary">{description}</p>}
        </div>
        {action && <div className="w-full 2xl:w-auto 2xl:shrink-0">{action}</div>}
      </div>
    );
  }

  return (
    <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
      <div>
        <h1 className="text-2xl font-semibold text-dt-text-primary">{title}</h1>
        {description && <p className="mt-1 text-sm text-dt-text-secondary">{description}</p>}
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </div>
  );
}
