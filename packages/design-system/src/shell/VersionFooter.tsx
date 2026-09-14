/**
 * Per-application version/build metadata, rendered in each app's footer
 * area (see docs/platform/versioning.md for the full convention).
 *
 * Presentation-only: this component owns no global version state and reads
 * no `process.env` itself. Each consuming app resolves its OWN metadata
 * (its own package.json version, its own build-time NEXT_PUBLIC_GIT_SHA /
 * NEXT_PUBLIC_BUILD_DATE, and — where wired — its own runtime RELEASE_DATE)
 * and supplies it as props at the call site — that is what makes "every
 * app owns its own version" independently auditable by reading each app's
 * own shell file, rather than trusting a comment inside a shared
 * component.
 *
 * Three lines, each a distinct concept — never collapsed into one:
 *   1. App name · by Dijital Team
 *   2. Semantic version · the exact commit the artifact was built from
 *   3. The real release/deploy date, labelled "Released" — never the
 *      artifact's build date relabelled. `releaseDate` is genuinely
 *      optional: an app that hasn't wired its runtime RELEASE_DATE source
 *      yet simply omits this line entirely rather than showing a fake or
 *      misleading value.
 */
export function VersionFooter({
  appName,
  version,
  gitSha,
  releaseDate,
  tone = "dark",
}: {
  appName: string;
  version: string;
  /** The commit the running artifact was built from. May legitimately
   * match across apps built from the same monorepo commit — never faked
   * to look different. */
  gitSha: string;
  /** The real deploy/release date for THIS app, sourced at runtime (never
   * baked at build time — see docs/platform/versioning.md for why a plain
   * build-time value must not be relabelled as this). Omitted entirely,
   * never fabricated, when not yet available for a given app. */
  releaseDate?: string | null;
  /** "dark" (default) for the sidebar's dark-gradient background; "light"
   * for a white/surface background (header-shell apps — Supplier Portal,
   * TalentFlow Client Portal). */
  tone?: "dark" | "light";
}) {
  const releaseDateShort = releaseDate ? releaseDate.slice(0, 10) : null;

  const labelClass = tone === "dark" ? "text-white/70" : "text-dt-text-secondary";
  const metaClass = tone === "dark" ? "text-white/40" : "text-dt-text-secondary/60";

  return (
    <div className="space-y-0.5">
      <p className={`text-xs font-medium ${labelClass}`}>{appName} · by Dijital Team</p>
      <p className={`font-mono text-[10px] tracking-tight ${metaClass}`} title={`${appName} v${version}`}>
        v{version} · Build {gitSha}
      </p>
      {releaseDateShort && (
        <p className={`font-mono text-[10px] tracking-tight ${metaClass}`} title={`Released ${releaseDate}`}>
          Released {releaseDateShort}
        </p>
      )}
    </div>
  );
}
