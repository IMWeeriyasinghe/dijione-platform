import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { VersionFooter } from "@dijione/design-system";

// Footer version/build metadata (docs/platform/versioning.md) — exercises
// the REAL @dijione/design-system component (not mocked). VersionFooter is
// presentation-only: it takes appName/version/gitSha/buildDate as props and
// reads no process.env itself, so each app's shell (not this shared
// component) is what makes the metadata app-specific.

describe("VersionFooter (per-app footer version/build metadata, prop-driven)", () => {
  it("renders the app name, version, git SHA, and a 'Built' date — never a bare date", () => {
    render(
      <VersionFooter appName="DijiBirthday" version="1.0.1" gitSha="394527a" buildDate="2026-09-14T08:30:00Z" />
    );

    expect(screen.getByText("DijiBirthday · by Dijital Team")).toBeInTheDocument();
    expect(screen.getByText("v1.0.1 · 394527a · Built 2026-09-14")).toBeInTheDocument();
    // Never mislabel a build timestamp as a release date.
    expect(screen.queryByText(/Release date/i)).not.toBeInTheDocument();
  });

  it("omits the build-date segment entirely when none was provided (e.g. `next dev`)", () => {
    render(<VersionFooter appName="DijiBirthday" version="0.0.0" gitSha="dev" />);

    expect(screen.getByText("v0.0.0 · dev")).toBeInTheDocument();
    expect(screen.queryByText(/Built/)).not.toBeInTheDocument();
  });

  it("renders two instances simultaneously with different props showing distinct values at once — proves no shared/global state inside the component", () => {
    render(
      <div>
        <div data-testid="birthday">
          <VersionFooter appName="DijiBirthday" version="1.0.1" gitSha="394527a" buildDate="2026-09-14" />
        </div>
        <div data-testid="talent">
          <VersionFooter appName="DijiTalentFlow" version="1.2.0" gitSha="394527a" buildDate="2026-09-14" />
        </div>
      </div>
    );

    expect(within(screen.getByTestId("birthday")).getByText("DijiBirthday · by Dijital Team")).toBeInTheDocument();
    expect(within(screen.getByTestId("birthday")).getByText("v1.0.1 · 394527a · Built 2026-09-14")).toBeInTheDocument();

    expect(within(screen.getByTestId("talent")).getByText("DijiTalentFlow · by Dijital Team")).toBeInTheDocument();
    expect(within(screen.getByTestId("talent")).getByText("v1.2.0 · 394527a · Built 2026-09-14")).toBeInTheDocument();

    // Same Git SHA (both released from the same commit) is legitimate and
    // expected; the version is what's independently owned per app.
    expect(within(screen.getByTestId("birthday")).queryByText(/v1\.2\.0/)).not.toBeInTheDocument();
    expect(within(screen.getByTestId("talent")).queryByText(/v1\.0\.1/)).not.toBeInTheDocument();
  });

  it("uses light-toned text classes for tone='light' (header-shell apps on a white surface)", () => {
    render(<VersionFooter appName="Supplier Portal" version="1.0.1" gitSha="394527a" tone="light" />);

    expect(screen.getByText("Supplier Portal · by Dijital Team")).toHaveClass("text-dt-text-secondary");
  });

  it("defaults to the dark tone when none is specified (sidebar's dark-gradient background)", () => {
    render(<VersionFooter appName="DijiOne" version="1.0.1" gitSha="394527a" />);

    expect(screen.getByText("DijiOne · by Dijital Team")).toHaveClass("text-white/70");
  });
});
