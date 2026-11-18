import { describe, expect, it } from "vitest";
import { buildSections } from "@/app/atwork-shell";
import { PERM, type AtworkScope } from "@/lib/atwork-scope";

const USER = [PERM.ACCESS, PERM.READ_OWN, PERM.RECORD_OWN, PERM.REQUEST_OWN];
const labels = (permissions: string[]) =>
  buildSections({ role: "ATWORK_USER", permissions } as AtworkScope).flatMap((s) => s.items.map((i) => `${s.label ?? ""}/${i.label}`));

describe("DijiAtWork Management → Access", () => {
  it("an appointed administrator with standard access sees their own pages plus Management → Access only", () => {
    expect(labels([...USER, PERM.ACCESS_MANAGE])).toEqual(["/Today", "/My Attendance", "/My Requests", "Management/Access"]);
  });

  it("a manager who is also an administrator sees Access inside Management", () => {
    const items = labels([...USER, PERM.MANAGEMENT, PERM.READ_ALL, PERM.ACCESS_MANAGE]);
    expect(items).toContain("Management/Employees");
    expect(items).toContain("Management/Access");
  });

  it("nobody else sees Access", () => {
    expect(labels([...USER, PERM.MANAGEMENT, PERM.READ_ALL]).some((l) => l.endsWith("/Access"))).toBe(false);
  });
});
