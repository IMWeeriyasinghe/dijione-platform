import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { AtworkContent, buildSections } from "@/app/atwork-shell";
import { RequirePermission } from "@/components/ui";
import { PERM, type AtworkScope } from "@/lib/atwork-scope";

const ACCESS_ONLY: AtworkScope = { role: "ATWORK_USER", permissions: [PERM.ACCESS] };
const scopeMock = vi.hoisted(() => ({ value: null as AtworkScope | null }));
const shellProps = vi.hoisted(() => ({ value: {} as Record<string, unknown> }));

vi.mock("@/lib/atwork-scope", async (orig) => {
  const actual = await orig<typeof import("@/lib/atwork-scope")>();
  return { ...actual, useAtworkScope: () => ({ loading: false, failed: false, scope: scopeMock.value, retry: vi.fn() }) };
});
vi.mock("@dijione/design-system", async (orig) => {
  const actual = await orig<typeof import("@dijione/design-system")>();
  return {
    ...actual,
    AppShell: (props: { children: React.ReactNode } & Record<string, unknown>) => {
      shellProps.value = props;
      return <main>{props.children}</main>;
    },
  };
});

describe("collapsible DijiAtWork sidebar", () => {
  it("opts in to the shared AppShell collapsible navigation with its own remembered preference", () => {
    scopeMock.value = { role: "ATWORK_USER", permissions: [PERM.ACCESS, PERM.READ_OWN] };
    render(<AtworkContent>page</AtworkContent>);
    expect(shellProps.value.collapsible).toEqual({ storageKey: "atwork.nav.collapsed" });
  });
});

describe("default access without an attendance identity", () => {
  it("has no attendance navigation", () => {
    expect(buildSections(ACCESS_ONLY)).toEqual([]);
  });

  it("explains why attendance is unavailable instead of a generic role message", () => {
    scopeMock.value = ACCESS_ONLY;
    render(
      <RequirePermission permission={PERM.READ_OWN} title="Attendance is not set up for your account"
        description="not linked to an employee record">
        <p>today</p>
      </RequirePermission>,
    );
    expect(screen.getByText("Attendance is not set up for your account")).toBeInTheDocument();
    expect(screen.getByText("not linked to an employee record")).toBeInTheDocument();
    expect(screen.queryByText("today")).not.toBeInTheDocument();
  });
});
