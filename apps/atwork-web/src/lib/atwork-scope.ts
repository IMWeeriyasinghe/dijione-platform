"use client";

import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { request, useAuth } from "@dijione/auth-client";

// The role and permissions come from atwork-api's /me, which reads the
// verified token. This drives navigation only; the API enforces access.
export const PERM = {
  ADMIN_AREA: "atwork.overview.read",
} as const;

export type AtworkScope = {
  role: string | null;
  permissions: string[];
};

export type AtworkMe = {
  user_id: number;
  full_name: string;
  module_access: boolean;
  role: string | null;
  permissions: string[];
};

export function resolveAtworkScope(me: AtworkMe | null | undefined): AtworkScope | null {
  if (!me?.module_access || me.permissions.length === 0) return null;
  return { role: me.role, permissions: [...me.permissions].sort() };
}

export function hasPermission(scope: AtworkScope | null | undefined, key: string): boolean {
  return Boolean(scope?.permissions.includes(key));
}

export function useAtworkScope(): { loading: boolean; failed: boolean; scope: AtworkScope | null; retry: () => void } {
  const { user, loading } = useAuth();
  const me = useQuery({
    queryKey: ["atwork-me", user?.id],
    queryFn: () => request<AtworkMe>("/api/atwork/me"),
    enabled: Boolean(user),
    retry: false,
    staleTime: 60_000,
  });
  const { isLoading, isError, data, refetch } = me;
  return useMemo(
    () => ({
      loading: loading || (Boolean(user) && isLoading),
      failed: isError,
      scope: isError ? null : resolveAtworkScope(data),
      retry: () => void refetch(),
    }),
    [loading, user, isLoading, isError, data, refetch],
  );
}
