"use client";

import { EmptyState } from "@dijione/design-system";
import { FuturePlaceholder } from "@/components/FuturePlaceholder";
import { hasPermission, PERM, useAtworkScope } from "@/lib/atwork-scope";

export default function ManagementPage() {
  const { scope } = useAtworkScope();
  if (!hasPermission(scope, PERM.MANAGEMENT)) {
    return <EmptyState title="Management access required" description="This area is limited to DijiAtWork managers." />;
  }
  return <FuturePlaceholder title="Management" description="DijiAtWork management tools will appear here." />;
}
