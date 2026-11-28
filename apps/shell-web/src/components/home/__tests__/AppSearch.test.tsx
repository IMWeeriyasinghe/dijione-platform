import { render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { AppSearch } from "../AppSearch";
import type { ModuleOut } from "@dijione/contracts";

// ModuleIcon pulls lucide-react icons dynamically — stub the whole module.
vi.mock("@/lib/module-icons", () => ({
  ModuleIcon: () => null,
}));

const ACTIVE: ModuleOut = {
  id: 1,
  key: "talent-flow",
  name: "DijiTalentFlow",
  description: "Talent Operations and Client Tracking",
  icon: "Users",
  route: "/talent",
  status: "ACTIVE",
  enabled: true,
  display_order: 1,
};

const COMING: ModuleOut = {
  id: 6,
  key: "alerts",
  name: "DijiALERTS",
  description: "Smart SMS Broadcasting & Emergency Communications",
  icon: "BellAlert",
  route: "/alerts",
  status: "COMING_SOON",
  enabled: true,
  display_order: 6,
};

function renderSearch(query = "", onQueryChange = vi.fn()) {
  const result = render(
    <AppSearch
      modules={[ACTIVE, COMING]}
      query={query}
      onQueryChange={onQueryChange}
    />,
  );
  // Focus opens the dropdown; required for all result-visibility assertions.
  if (query) fireEvent.focus(result.getByRole("combobox"));
  return result;
}

describe("AppSearch", () => {
  it("renders the search input", () => {
    renderSearch();
    expect(screen.getByRole("combobox")).toBeTruthy();
  });

  it("calls onQueryChange when the user types", () => {
    const onQueryChange = vi.fn();
    renderSearch("", onQueryChange);
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "diji" } });
    expect(onQueryChange).toHaveBeenCalledWith("diji");
  });

  it("shows matching results for an active module", () => {
    renderSearch("talent");
    expect(screen.getByText("DijiTalentFlow")).toBeTruthy();
  });

  it("shows Coming Soon results but marks them as non-navigable", () => {
    renderSearch("alerts");
    expect(screen.getByText("DijiALERTS")).toBeTruthy();
    expect(screen.getByText("Soon")).toBeTruthy();
  });

  it("shows no-match message when nothing found", () => {
    renderSearch("zzznomatch");
    expect(screen.getByText(/No applications match/)).toBeTruthy();
  });

  it("shows the clear button when query is non-empty and calls onQueryChange with empty string", () => {
    const onQueryChange = vi.fn();
    renderSearch("diji", onQueryChange);
    const clearBtn = screen.getByRole("button", { name: /clear search/i });
    expect(clearBtn).toBeTruthy();
    fireEvent.click(clearBtn);
    expect(onQueryChange).toHaveBeenCalledWith("");
  });

  it("matches by description as well as name", () => {
    renderSearch("emergency");
    expect(screen.getByText("DijiALERTS")).toBeTruthy();
  });

  it("filters results — only matches are shown, not all modules", () => {
    renderSearch("talent");
    expect(screen.getByText("DijiTalentFlow")).toBeTruthy();
    expect(screen.queryByText("DijiALERTS")).toBeNull();
  });
});
