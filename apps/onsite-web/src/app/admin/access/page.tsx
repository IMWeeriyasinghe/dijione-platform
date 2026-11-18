"use client";

import { AccessManagementPage } from "@dijione/design-system";
import { AdminOnly } from "@/components/AdminOnly";
import { PERM } from "@/lib/onsite-scope";

export default function AccessPage() {
  return (
    <AdminOnly permission={PERM.ACCESS_MANAGE}>
      <AccessManagementPage moduleKey="onsite" appName="Diji On-site" />
    </AdminOnly>
  );
}
