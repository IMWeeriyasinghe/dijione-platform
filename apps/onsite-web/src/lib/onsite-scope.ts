"use client";

import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { request, useAuth } from "@dijione/auth-client";

// On-site-specific scope interpretation lives in this module only (rule 6).
// The effective role and permission list come from onsite-api's /me, which
// reads the verified JWT claim (direct + access-group grants). This drives
// navigation and buttons only — onsite-api re-checks every permission.
export const MODULE_ONSITE = "onsite";
export const ONSITE_ADMIN_ROLE = "ONSITE_ADMIN";

/** Permission keys that gate On-site UI, mirroring onsite-api's checks. */
export const PERM = {
  HEALTH: "onsite.health.read",
  IDENTITY: "onsite.identity.read",
  SYNC: "onsite.sync.request",
  SITES: "onsite.sites.manage",
} as const;

export type OnsiteScope = {
  role: string;
  permissions: string[];
};

type OnsiteMe = { role: string; permissions: string[] };

export function resolveOnsiteScope(me: OnsiteMe | null | undefined): OnsiteScope | null {
  if (!me || !Array.isArray(me.permissions) || me.permissions.length === 0) return null;
  return { role: me.role, permissions: [...me.permissions].sort() };
}

export function hasPermission(scope: OnsiteScope | null | undefined, key: string): boolean {
  return Boolean(scope?.permissions.includes(key));
}

export function useOnsiteScope(): { loading: boolean; scope: OnsiteScope | null } {
  const { user, loading } = useAuth();
  const me = useQuery({
    queryKey: ["onsite-me", user?.id],
    queryFn: () => request<OnsiteMe>("/api/onsite/me"),
    enabled: Boolean(user),
    retry: false,
    staleTime: 60_000,
  });
  return useMemo(
    () => ({
      loading: loading || (Boolean(user) && me.isLoading),
      scope: me.isError ? null : resolveOnsiteScope(me.data),
    }),
    [loading, user, me.isLoading, me.isError, me.data],
  );
}
