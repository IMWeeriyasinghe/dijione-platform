/**
 * Per-application version/build metadata, rendered in each app's Sidebar
 * footer slot (see docs/platform/versioning.md for the full convention).
 *
 * Deliberately reads `process.env.NEXT_PUBLIC_*` directly in this shared
 * component rather than taking version/sha/date as props: each consuming
 * app transpiles this package into its OWN Next.js build
 * (`transpilePackages`), so Next's build-time env replacement substitutes
 * a different literal value per app — the same component code yields
 * app-specific output with zero per-app plumbing beyond each app's own
 * next.config.ts (which reads its own package.json version + the
 * GIT_SHA/BUILD_DATE build args). This is what keeps the platform from
 * ever showing one shared DijiOne-wide version number by accident.
 */
export function VersionFooter({
  appLabel,
  tone = "dark",
}: {
  appLabel: string;
  /** "dark" (default) for the sidebar's dark-gradient background; "light"
   * for a white/surface background (the two apps with a header-based shell
   * instead of a sidebar — Supplier Portal, TalentFlow Client Portal). */
  tone?: "dark" | "light";
}) {
  const version = process.env.NEXT_PUBLIC_APP_VERSION || "0.0.0";
  const gitSha = process.env.NEXT_PUBLIC_GIT_SHA || "dev";
  const buildDate = process.env.NEXT_PUBLIC_BUILD_DATE;
  const buildDateShort = buildDate ? buildDate.slice(0, 10) : null;

  const labelClass = tone === "dark" ? "text-white/70" : "text-dt-text-secondary";
  const metaClass = tone === "dark" ? "text-white/40" : "text-dt-text-secondary/60";

  return (
    <div className="space-y-0.5">
      <p className={`text-xs font-medium ${labelClass}`}>{appLabel} · by Dijital Team</p>
      <p
        className={`font-mono text-[10px] tracking-tight ${metaClass}`}
        title={buildDate ? `${appLabel} v${version} · commit ${gitSha} · built ${buildDate}` : undefined}
      >
        v{version} · {gitSha}
        {buildDateShort && ` · ${buildDateShort}`}
      </p>
    </div>
  );
}
