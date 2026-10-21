import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { resolveOnsiteScope } from "@/lib/onsite-scope";
import { buildSections } from "@/app/onsite-shell";

const scopeMock = vi.hoisted(() => ({ value: { loading: false, scope: null as null | { role: string; isAdmin: boolean } } }));
vi.mock("@/lib/onsite-scope", async (orig) => {
  const actual = await orig<typeof import("@/lib/onsite-scope")>();
  return { ...actual, useOnsiteScope: () => scopeMock.value };
});

describe("resolveOnsiteScope", () => {
  it("returns null without an On-site role", () => {
    expect(resolveOnsiteScope(undefined)).toBeNull();
    expect(resolveOnsiteScope([{ module_key: "birthday", role: "BIRTHDAY_ADMIN" }])).toBeNull();
  });
  it("ignores disabled assignments and unknown roles", () => {
    expect(resolveOnsiteScope([{ module_key: "onsite", role: "ONSITE_ADMIN", enabled: false }])).toBeNull();
    expect(resolveOnsiteScope([{ module_key: "onsite", role: "SOMETHING_ELSE" }])).toBeNull();
  });
  it("distinguishes viewer and admin", () => {
    expect(resolveOnsiteScope([{ module_key: "onsite", role: "ONSITE_VIEWER" }])).toEqual({ role: "ONSITE_VIEWER", isAdmin: false });
    expect(resolveOnsiteScope([{ module_key: "onsite", role: "ONSITE_ADMIN" }])).toEqual({ role: "ONSITE_ADMIN", isAdmin: true });
  });
});

describe("navigation", () => {
  const labels = (isAdmin: boolean) => buildSections(isAdmin).flatMap((s) => s.items.map((i) => i.label));

  it("viewer sees the dashboard navigation only", () => {
    expect(labels(false)).toEqual(["Overview", "Today", "Activity", "Employees", "Exceptions"]);
  });
  it("admin also sees the admin section", () => {
    expect(labels(true)).toEqual([
      "Overview", "Today", "Activity", "Employees", "Exceptions", "Site Health", "Identity Match", "Sites",
    ]);
  });
  it("never uses policy wording", () => {
    const all = labels(true).join(" ").toLowerCase();
    for (const word of ["present", "absent", "late", "early", "working hours"]) expect(all).not.toContain(word);
  });
});

describe("access states", () => {
  it("shows the no-access state without an On-site role", async () => {
    scopeMock.value = { loading: false, scope: null };
    const { OnsiteContent } = await import("@/app/onsite-shell");
    render(<OnsiteContent><p>secret</p></OnsiteContent>);
    expect(screen.getByText("No Diji On-site access")).toBeInTheDocument();
    expect(screen.queryByText("secret")).not.toBeInTheDocument();
  });

  it("shows a loading state while access is resolved", async () => {
    scopeMock.value = { loading: true, scope: null };
    const { OnsiteContent } = await import("@/app/onsite-shell");
    render(<OnsiteContent><p>secret</p></OnsiteContent>);
    expect(screen.getByText("Checking access…")).toBeInTheDocument();
  });

  it("blocks admin pages for viewers", async () => {
    scopeMock.value = { loading: false, scope: { role: "ONSITE_VIEWER", isAdmin: false } };
    const { AdminOnly } = await import("@/components/AdminOnly");
    render(<AdminOnly><p>admin content</p></AdminOnly>);
    expect(screen.getByText("Administrator access required")).toBeInTheDocument();
    expect(screen.queryByText("admin content")).not.toBeInTheDocument();
  });

  it("allows admin pages for admins", async () => {
    scopeMock.value = { loading: false, scope: { role: "ONSITE_ADMIN", isAdmin: true } };
    const { AdminOnly } = await import("@/components/AdminOnly");
    render(<AdminOnly><p>admin content</p></AdminOnly>);
    expect(screen.getByText("admin content")).toBeInTheDocument();
  });
});
