"use client";

import { EmptyState } from "@dijione/design-system";
import { ShieldAlert } from "lucide-react";
import { hasPermission, useOnsiteScope } from "@/lib/onsite-scope";

/** Hides an admin page unless the caller holds ``permission``. Convenience
 *  only — onsite-api enforces the same permission independently (403). */
export function AdminOnly({ permission, children }: { permission: string; children: React.ReactNode }) {
  const { scope } = useOnsiteScope();
  if (!hasPermission(scope, permission)) {
    return (
      <EmptyState
        icon={ShieldAlert}
        title="Administrator access required"
        description="This page is available to Diji On-site administrators only."
      />
    );
  }
  return <>{children}</>;
}
