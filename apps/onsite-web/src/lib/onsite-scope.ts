"use client";

import { useMemo } from "react";
import { useAuth } from "@dijione/auth-client";

// On-site-specific scope interpretation lives in this module only (rule 6):
// the shared auth package provides the generic session; this file decides
// what it means for Diji On-site. The backend re-checks every permission —
// this is navigation convenience, never authorization.
export const MODULE_ONSITE = "onsite";
export const ONSITE_ADMIN_ROLE = "ONSITE_ADMIN";
export const ONSITE_ROLES = new Set(["ONSITE_VIEWER", ONSITE_ADMIN_ROLE]);

export type OnsiteScope = {
  role: string;
  isAdmin: boolean;
};

export function resolveOnsiteScope(
  moduleRoles: { module_key: string; role: string; enabled?: boolean }[] | undefined,
): OnsiteScope | null {
  const role = moduleRoles?.find((r) => r.module_key === MODULE_ONSITE && r.enabled !== false);
  if (!role || !ONSITE_ROLES.has(role.role)) return null;
  return { role: role.role, isAdmin: role.role === ONSITE_ADMIN_ROLE };
}

export function useOnsiteScope(): { loading: boolean; scope: OnsiteScope | null } {
  const { user, loading } = useAuth();
  return useMemo(
    () => ({ loading, scope: user ? resolveOnsiteScope(user.module_roles) : null }),
    [user, loading],
  );
}
