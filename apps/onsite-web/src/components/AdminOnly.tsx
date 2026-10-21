"use client";

import { EmptyState } from "@dijione/design-system";
import { ShieldAlert } from "lucide-react";
import { useOnsiteScope } from "@/lib/onsite-scope";

/** Hides admin pages from viewers. Convenience only — onsite-api enforces
 *  every admin permission independently (403). */
export function AdminOnly({ children }: { children: React.ReactNode }) {
  const { scope } = useOnsiteScope();
  if (!scope?.isAdmin) {
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
