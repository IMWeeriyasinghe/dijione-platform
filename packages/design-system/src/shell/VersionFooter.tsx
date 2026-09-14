/**
 * Per-application version/build metadata, rendered in each app's footer
 * area (see docs/platform/versioning.md for the full convention).
 *
 * Presentation-only: this component owns no global version state and reads
 * no `process.env` itself. Each consuming app resolves its OWN metadata
 * (its own package.json version, its own build-time NEXT_PUBLIC_GIT_SHA /
 * NEXT_PUBLIC_BUILD_DATE) and supplies it as props at the call site — that
 * is what makes "every app owns its own version" independently auditable
 * by reading each app's own shell file, rather than trusting a comment
 * inside a shared component.
 *
 * `buildDate` is the artifact BUILD date (when the image was built), never
 * a deployment/release date — those are different concepts. If a separate
 * true release timestamp is ever needed, it is a distinct RELEASE_DATE
 * value, not this one; see docs/platform/versioning.md.
 */
export function VersionFooter({
  appName,
  version,
  gitSha,
  buildDate,
  tone = "dark",
}: {
  appName: string;
  version: string;
  gitSha: string;
  /** ISO date/timestamp string, or undefined if not available (e.g. `next dev`). */
  buildDate?: string;
  /** "dark" (default) for the sidebar's dark-gradient background; "light"
   * for a white/surface background (header-shell apps — Supplier Portal,
   * TalentFlow Client Portal). */
  tone?: "dark" | "light";
}) {
  const buildDateShort = buildDate ? buildDate.slice(0, 10) : null;

  const labelClass = tone === "dark" ? "text-white/70" : "text-dt-text-secondary";
  const metaClass = tone === "dark" ? "text-white/40" : "text-dt-text-secondary/60";

  return (
    <div className="space-y-0.5">
      <p className={`text-xs font-medium ${labelClass}`}>{appName} · by Dijital Team</p>
      <p
        className={`font-mono text-[10px] tracking-tight ${metaClass}`}
        title={buildDate ? `${appName} v${version} · commit ${gitSha} · built ${buildDate}` : undefined}
      >
        v{version} · {gitSha}
        {buildDateShort && ` · Built ${buildDateShort}`}
      </p>
    </div>
  );
}
