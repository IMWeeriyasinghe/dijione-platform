import { cn } from "../utils";

/**
 * The official Dijital Team wordmark (black lowercase "dijital team", the
 * "j" ascender replaced by a four-dot stack: yellow / orange / red /
 * green). One asset, referenced from each app's own `public/brand/`
 * (Next.js only serves an app's own `public/`, not a package's).
 *
 * `variant="light"` renders the guideline-sanctioned white/reversed
 * treatment for dark backgrounds — a pure-white recolour of the same
 * wordmark via a CSS filter, which preserves the geometry exactly (not a
 * different colour, not a redraw). Per the brand guide, the reversed logo
 * is white text only.
 *
 * Never stretch/distort, never recolour beyond the sanctioned white
 * version, keep clear space (~2× the dot width) around it, min ~120px
 * wide on screen without a tagline. Taglines are never used in
 * operational app chrome.
 */
export function BrandLogo({
  variant = "dark",
  className,
  width = 140,
  alt = "Dijital Team",
}: {
  variant?: "dark" | "light";
  className?: string;
  width?: number;
  alt?: string;
}) {
  return (
    // eslint-disable-next-line @next/next/no-img-element -- a fixed static
    // brand asset served from each app's own public/; next/image's
    // optimizer/basePath handling adds nothing and complicates cross-zone
    // rewrites (same reasoning as Sidebar's <Image unoptimized>).
    <img
      src="/brand/dijital-team-logo.png"
      alt={alt}
      width={width}
      className={cn(
        "h-auto max-w-full object-contain",
        // brightness(0) collapses the wordmark to pure black first, so
        // invert(1) yields a clean pure-white regardless of the source's
        // anti-aliased edges.
        variant === "light" && "[filter:brightness(0)_invert(1)]",
        className,
      )}
    />
  );
}
