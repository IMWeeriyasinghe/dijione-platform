"use client";

import { useTalentScope } from "@dijione/auth-client";
import { AccessManagementPage, EmptyState } from "@dijione/design-system";

export default function AccessPage() {
  const scope = useTalentScope();
  if (!scope?.canManageAccess) {
    return <EmptyState title="Access administration required" description="Only appointed access administrators can manage DijiTalentFlow access." />;
  }
  return <AccessManagementPage moduleKey="talent-flow" appName="DijiTalentFlow" />;
}
