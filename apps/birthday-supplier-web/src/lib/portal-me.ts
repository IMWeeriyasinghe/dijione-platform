"use client";

import { useQuery } from "@tanstack/react-query";
import { getPortalMe, type PortalMe } from "@/lib/api";
import { useSupplierAuth } from "@/lib/supplier-auth";

/** Session identity + whether this is a read-only internal preview (§C).
 * react-query dedupes this across the shell, order detail, and timeline. */
export function usePortalMe(): PortalMe | undefined {
  const { token } = useSupplierAuth();
  const { data } = useQuery({
    queryKey: ["portal-me"],
    queryFn: () => getPortalMe(token!),
    enabled: !!token,
    staleTime: 60_000,
  });
  return data;
}
