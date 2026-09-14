import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { VersionFooter } from "@dijione/design-system";

// Footer version/build metadata (docs/platform/versioning.md) — exercises
// the REAL @dijione/design-system component (not mocked). VersionFooter is
// presentation-only: it takes appName/version/gitSha/releaseDate as props
// and reads no process.env itself. Round 3: 3 distinct lines — app name,
// version+build-SHA, and a genuinely-optional real release date (never a
// relabelled build date).

describe("VersionFooter (3-line format, round 3)", () => {
  it("renders three lines: app name, version+build SHA, and Released date", () => {
    render(<VersionFooter appName="DijiBirthday" version="1.0.2" gitSha="9ea594ddd113" releaseDate="2026-09-14T10:42:00Z" />);

    expect(screen.getByText("DijiBirthday · by Dijital Team")).toBeInTheDocument();
    expect(screen.getByText("v1.0.2 · Build 9ea594ddd113")).toBeInTheDocument();
    expect(screen.getByText("Released 2026-09-14")).toBeInTheDocument();
  });

  it("never labels the git SHA line as a release/build date, and never mislabels the date line", () => {
    render(<VersionFooter appName="DijiBirthday" version="1.0.2" gitSha="abc123" releaseDate="2026-09-14" />);

    expect(screen.queryByText(/Build date/i)).not.toBeInTheDocument();
    expect(screen.getByText("v1.0.2 · Build abc123")).toBeInTheDocument(); // "Build" labels the SHA, not a date
  });

  it("omits the Released line entirely when releaseDate is unavailable — never a fake value", () => {
    render(<VersionFooter appName="DijiBirthday" version="0.0.0" gitSha="dev" />);

    expect(screen.getByText("v0.0.0 · Build dev")).toBeInTheDocument();
    expect(screen.queryByText(/Released/)).not.toBeInTheDocument();
  });

  it("also omits the Released line when releaseDate is explicitly null (the /api/meta shape before RELEASE_DATE is set)", () => {
    render(<VersionFooter appName="DijiBirthday" version="1.0.2" gitSha="abc123" releaseDate={null} />);

    expect(screen.queryByText(/Released/)).not.toBeInTheDocument();
  });

  it("renders two instances simultaneously with different props showing distinct values at once — proves no shared/global state", () => {
    render(
      <div>
        <div data-testid="birthday">
          <VersionFooter appName="DijiBirthday" version="1.0.2" gitSha="9ea594d" releaseDate="2026-09-14" />
        </div>
        <div data-testid="talent">
          <VersionFooter appName="DijiTalentFlow" version="1.0.1" gitSha="9ea594d" />
        </div>
      </div>
    );

    expect(within(screen.getByTestId("birthday")).getByText("v1.0.2 · Build 9ea594d")).toBeInTheDocument();
    expect(within(screen.getByTestId("birthday")).getByText("Released 2026-09-14")).toBeInTheDocument();

    expect(within(screen.getByTestId("talent")).getByText("v1.0.1 · Build 9ea594d")).toBeInTheDocument();
    expect(within(screen.getByTestId("talent")).queryByText(/Released/)).not.toBeInTheDocument();
  });

  it("uses light-toned text classes for tone='light' (header-shell apps on a white surface)", () => {
    render(<VersionFooter appName="Supplier Portal" version="1.0.1" gitSha="abc123" tone="light" />);

    expect(screen.getByText("Supplier Portal · by Dijital Team")).toHaveClass("text-dt-text-secondary");
  });

  it("defaults to the dark tone when none is specified (sidebar's dark-gradient background)", () => {
    render(<VersionFooter appName="DijiOne" version="1.0.1" gitSha="abc123" />);

    expect(screen.getByText("DijiOne · by Dijital Team")).toHaveClass("text-white/70");
  });
});
