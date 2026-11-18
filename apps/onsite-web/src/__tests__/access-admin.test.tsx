import { describe, expect, it } from "vitest";
import { buildSections } from "@/app/onsite-shell";
import { isAccessAdminOnly, PERM } from "@/lib/onsite-scope";

const scope = (permissions: string[]) => ({ role: "X", permissions });
const labels = (permissions: string[]) => buildSections(scope(permissions)).flatMap((s) => s.items.map((i) => i.label));

describe("Diji On-site Admin → Access", () => {
  it("an access administrator with no business role sees only Access", () => {
    expect(isAccessAdminOnly(scope([PERM.ACCESS_MANAGE]))).toBe(true);
    expect(labels([PERM.ACCESS_MANAGE])).toEqual(["Access"]);
  });

  it("a viewer who is also an administrator keeps the business pages and gains Access", () => {
    const perms = [PERM.DASHBOARD, "onsite.attendance.read", PERM.ACCESS_MANAGE];
    expect(isAccessAdminOnly(scope(perms))).toBe(false);
    expect(labels(perms)).toEqual(["Overview", "Today", "Activity", "Team Members", "Exceptions", "Access"]);
  });

  it("nobody else sees Access", () => {
    expect(labels([PERM.DASHBOARD, PERM.SITES])).not.toContain("Access");
  });
});
