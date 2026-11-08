"use client";

import { EmptyState } from "@dijione/design-system";
import { FuturePlaceholder } from "@/components/FuturePlaceholder";
import { hasPermission, PERM, useAtworkScope } from "@/lib/atwork-scope";

export default function AdminPage() {
  const { scope } = useAtworkScope();
  if (!hasPermission(scope, PERM.ADMIN_AREA)) {
    return <EmptyState title="Administrator access required" description="This area is limited to DijiAtWork administrators." />;
  }
  return <FuturePlaceholder title="Administration" description="Oversight tools will appear here." />;
}
