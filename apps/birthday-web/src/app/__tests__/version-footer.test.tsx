import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { VersionFooter } from "@dijione/design-system";

// Footer version/build metadata (docs/platform/versioning.md) — exercises
// the REAL @dijione/design-system component (not mocked). Since Next
// bakes NEXT_PUBLIC_* values in at build time via static replacement,
// process.env is only genuinely mutable here in a plain vitest run — this
// pins the fallback behaviour and the exact rendered format, which is what
// actually ships once a real build substitutes literals in.

const ENV_KEYS = ["NEXT_PUBLIC_APP_VERSION", "NEXT_PUBLIC_GIT_SHA", "NEXT_PUBLIC_BUILD_DATE"] as const;
const originalEnv: Record<string, string | undefined> = {};

beforeEach(() => {
  for (const key of ENV_KEYS) originalEnv[key] = process.env[key];
});

afterEach(() => {
  for (const key of ENV_KEYS) {
    if (originalEnv[key] === undefined) delete process.env[key];
    else process.env[key] = originalEnv[key];
  }
});

describe("VersionFooter (per-app footer version/build metadata)", () => {
  it("renders the app label, version, git SHA, and a short build date", () => {
    process.env.NEXT_PUBLIC_APP_VERSION = "1.0.0";
    process.env.NEXT_PUBLIC_GIT_SHA = "8a11d3e971b4";
    process.env.NEXT_PUBLIC_BUILD_DATE = "2026-09-14T08:30:00Z";

    render(<VersionFooter appLabel="DijiBirthday" />);

    expect(screen.getByText("DijiBirthday · by Dijital Team")).toBeInTheDocument();
    expect(screen.getByText("v1.0.0 · 8a11d3e971b4 · 2026-09-14")).toBeInTheDocument();
  });

  it("falls back to safe placeholders when nothing was baked in (e.g. `next dev`)", () => {
    delete process.env.NEXT_PUBLIC_APP_VERSION;
    delete process.env.NEXT_PUBLIC_GIT_SHA;
    delete process.env.NEXT_PUBLIC_BUILD_DATE;

    render(<VersionFooter appLabel="DijiBirthday" />);

    expect(screen.getByText("v0.0.0 · dev")).toBeInTheDocument();
  });

  it("omits the build date segment entirely when none was provided", () => {
    process.env.NEXT_PUBLIC_APP_VERSION = "1.0.0";
    process.env.NEXT_PUBLIC_GIT_SHA = "abc123";
    delete process.env.NEXT_PUBLIC_BUILD_DATE;

    render(<VersionFooter appLabel="DijiBirthday" />);

    expect(screen.getByText("v1.0.0 · abc123")).toBeInTheDocument();
  });

  it("shows a different app label per instance — never a shared platform-wide label", () => {
    process.env.NEXT_PUBLIC_APP_VERSION = "1.0.0";
    process.env.NEXT_PUBLIC_GIT_SHA = "abc123";

    const { rerender } = render(<VersionFooter appLabel="DijiBirthday" />);
    expect(screen.getByText("DijiBirthday · by Dijital Team")).toBeInTheDocument();

    rerender(<VersionFooter appLabel="DijiTalentFlow" />);
    expect(screen.getByText("DijiTalentFlow · by Dijital Team")).toBeInTheDocument();
    expect(screen.queryByText("DijiBirthday · by Dijital Team")).not.toBeInTheDocument();
  });

  it("uses light-toned text classes for tone='light' (header-shell apps on a white surface)", () => {
    process.env.NEXT_PUBLIC_APP_VERSION = "1.0.0";
    process.env.NEXT_PUBLIC_GIT_SHA = "abc123";

    render(<VersionFooter appLabel="Supplier Portal" tone="light" />);

    expect(screen.getByText("Supplier Portal · by Dijital Team")).toHaveClass("text-dt-text-secondary");
  });
});
