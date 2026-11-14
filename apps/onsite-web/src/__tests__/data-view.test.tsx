import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { DataView } from "@/components/DataView";

type Row = { id: string; name: string; extra: string };
const rows: Row[] = [{ id: "1", name: "Alpha", extra: "Only in details" }];
const view = () => render(
  <DataView<Row> caption="Rows" rows={rows} rowKey={(r) => r.id} rowLabel={(r) => r.name}
    columns={[
      { key: "name", header: "Name", cell: (r) => r.name },
      { key: "extra", header: "Extra field", minWidth: "xl", cell: (r) => r.extra },
    ]}
    card={(r) => <span>{r.name} card</span>} />,
);

function viewport(width: number) {
  vi.stubGlobal("matchMedia", (q: string) => ({
    matches: width >= Number(/(\d+)px/.exec(q)?.[1] ?? 0), media: q,
    addEventListener: () => {}, removeEventListener: () => {},
  }));
}

afterEach(() => vi.unstubAllGlobals());

describe("DataView responsive columns", () => {
  it("shows every column as a table column on wide screens", () => {
    viewport(1440);
    view();
    expect(screen.getByRole("columnheader", { name: "Extra field" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Show details/ })).not.toBeInTheDocument();
  });

  it("moves a column hidden at laptop width into the row details instead of dropping it", () => {
    viewport(1024);
    view();
    expect(screen.queryByRole("columnheader", { name: "Extra field" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Show details for Alpha" }));
    expect(screen.getByText("Extra field")).toBeInTheDocument();
    expect(screen.getByText("Only in details")).toBeInTheDocument();
  });

  it("uses cards below 1024 px", () => {
    viewport(768);
    view();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    expect(screen.getByText("Alpha card")).toBeInTheDocument();
  });

  it("renders a column help tip beside, never inside, the sort button", () => {
    viewport(1440);
    const { container } = render(
      <DataView<Row> caption="Sorted" rows={rows} rowKey={(r) => r.id} sort="name" onSort={() => {}}
        columns={[{ key: "name", header: "Name", sort: "name", help: "What the name is", cell: (r) => r.name }]}
        card={(r) => <span>{r.name}</span>} />,
    );
    expect(screen.getByRole("button", { name: "About Name" })).toBeInTheDocument();
    expect(container.querySelector("button button")).toBeNull();
  });
});
