"use client";

import { AccessManagementPage } from "@dijione/design-system";
import { Page, RequirePermission } from "@/components/ui";
import { PERM } from "@/lib/atwork-scope";

export default function AccessPage() {
  return (
    <Page>
      <RequirePermission permission={PERM.ACCESS_MANAGE} title="Access administration required">
        <AccessManagementPage moduleKey="atwork" appName="DijiAtWork" />
      </RequirePermission>
    </Page>
  );
}
