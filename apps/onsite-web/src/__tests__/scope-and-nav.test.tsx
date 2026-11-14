import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { PERM, resolveOnsiteScope, type OnsiteScope } from "@/lib/onsite-scope";
import { buildSections } from "@/app/onsite-shell";

const VIEWER = ["onsite.attendance.read", "onsite.dashboard.read", "onsite.exceptions.read"];
const ADMIN = [...VIEWER, "onsite.health.read", "onsite.identity.read", "onsite.sites.manage", "onsite.sync.request"];

const scopeMock = vi.hoisted(() => ({ value: { loading: false, scope: null as null | { role: string; permissions: string[] } } }));
vi.mock("@/lib/onsite-scope", async (orig) => {
  const actual = await orig<typeof import("@/lib/onsite-scope")>();
  return { ...actual, useOnsiteScope: () => scopeMock.value };
});

describe("resolveOnsiteScope (from onsite-api /me)", () => {
  it("returns null without On-site permissions", () => {
    expect(resolveOnsiteScope(undefined)).toBeNull();
    expect(resolveOnsiteScope(null)).toBeNull();
    expect(resolveOnsiteScope({ role: "ONSITE_VIEWER", permissions: [] })).toBeNull();
  });
  it("keeps role and permissions (direct or group-derived)", () => {
    expect(resolveOnsiteScope({ role: "ONSITE_VIEWER", permissions: VIEWER })).toEqual({ role: "ONSITE_VIEWER", permissions: VIEWER });
  });
});

describe("navigation follows permissions, not role names", () => {
  const labels = (scope: OnsiteScope | null) => buildSections(scope).flatMap((s) => s.items.map((i) => i.label));

  it("viewer sees the dashboard navigation only", () => {
    expect(labels({ role: "ONSITE_VIEWER", permissions: VIEWER })).toEqual(["Overview", "Today", "Activity", "Team Members", "Exceptions"]);
  });
  it("admin also sees the admin section", () => {
    expect(labels({ role: "ONSITE_ADMIN", permissions: ADMIN })).toEqual([
      "Overview", "Today", "Activity", "Team Members", "Exceptions", "Site Health", "Identity Management", "Sites",
    ]);
  });
  it("each admin page needs its own permission", () => {
    expect(labels({ role: "CUSTOM", permissions: [...VIEWER, PERM.HEALTH] })).toContain("Site Health");
    expect(labels({ role: "CUSTOM", permissions: [...VIEWER, PERM.HEALTH] })).not.toContain("Sites");
    expect(labels({ role: "ONSITE_ADMIN", permissions: VIEWER })).not.toContain("Site Health"); // role name alone grants nothing
  });
  it("never uses policy wording", () => {
    const all = labels({ role: "ONSITE_ADMIN", permissions: ADMIN }).join(" ").toLowerCase();
    for (const word of ["present", "absent", "late", "early", "working hours"]) expect(all).not.toContain(word);
  });
});

describe("access states", () => {
  it("shows the no-access state without On-site access", async () => {
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

  it("blocks an admin page without its permission", async () => {
    scopeMock.value = { loading: false, scope: { role: "ONSITE_VIEWER", permissions: VIEWER } };
    const { AdminOnly } = await import("@/components/AdminOnly");
    render(<AdminOnly permission={PERM.SITES}><p>admin content</p></AdminOnly>);
    expect(screen.getByText("Administrator access required")).toBeInTheDocument();
    expect(screen.queryByText("admin content")).not.toBeInTheDocument();
  });

  it("allows an admin page with its permission", async () => {
    scopeMock.value = { loading: false, scope: { role: "ONSITE_ADMIN", permissions: ADMIN } };
    const { AdminOnly } = await import("@/components/AdminOnly");
    render(<AdminOnly permission={PERM.SITES}><p>admin content</p></AdminOnly>);
    expect(screen.getByText("admin content")).toBeInTheDocument();
  });
});
