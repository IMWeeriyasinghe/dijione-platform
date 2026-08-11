"use client";

import { useTalentScope } from "@/lib/auth-context";
import { ClientDashboardView } from "@/components/talent/ClientDashboardView";
import { TaDashboardView } from "@/components/talent/TaDashboardView";

export default function DashboardPage() {
  const scope = useTalentScope();
  if (!scope) return null;
  return scope.isStaff ? <TaDashboardView /> : <ClientDashboardView />;
}
