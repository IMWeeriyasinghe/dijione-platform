"use client";

import { useBirthdayScope } from "@dijione/auth-client";
import { AccessManagementPage, EmptyState } from "@dijione/design-system";

/** Staff access (employees). Supplier users stay on the Suppliers pages. */
export default function AccessPage() {
  const scope = useBirthdayScope();
  if (!scope?.canManageAccess) {
    return <EmptyState title="Access administration required" description="Only appointed access administrators can manage DIJI Birthday staff access." />;
  }
  return <AccessManagementPage moduleKey="birthday" appName="DIJI Birthday" />;
}
