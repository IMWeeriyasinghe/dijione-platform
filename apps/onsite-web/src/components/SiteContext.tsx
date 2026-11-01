"use client";

import { createContext, useContext, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { EmptyState, ErrorState, LoadingState } from "@dijione/design-system";
import { MapPin } from "lucide-react";
import { getSitesInfo, type OnsiteSiteInfo } from "@/lib/dashboard";

type SiteContextValue = {
  sites: OnsiteSiteInfo[];
  site: OnsiteSiteInfo;
  setSiteId: (id: string) => void;
};

const SiteCtx = createContext<SiteContextValue | null>(null);
const STORAGE_KEY = "onsite.selectedSite";

function readStored(): string | null {
  try {
    return window.sessionStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

/** Shares the selected enabled site across the dashboard pages. Only sites
 *  an On-site Admin has enabled are ever listed (the API enforces it). */
export function SiteProvider({ children }: { children: React.ReactNode }) {
  const query = useQuery({ queryKey: ["onsite-sites"], queryFn: getSitesInfo, refetchInterval: 60_000 });
  const [siteId, setSiteIdState] = useState<string | null>(() => (typeof window === "undefined" ? null : readStored()));

  const value = useMemo<SiteContextValue | null>(() => {
    const sites = query.data ?? [];
    if (sites.length === 0) return null;
    const site = sites.find((s) => s.site_id === siteId) ?? sites[0];
    return {
      sites,
      site,
      setSiteId: (id: string) => {
        setSiteIdState(id);
        try {
          window.sessionStorage.setItem(STORAGE_KEY, id);
        } catch {
          /* per-tab convenience only */
        }
      },
    };
  }, [query.data, siteId]);

  if (query.isLoading) return <LoadingState label="Loading sites…" />;
  if (query.isError) return <ErrorState onRetry={() => query.refetch()} />;
  if (!value) {
    return (
      <EmptyState
        icon={MapPin}
        title="No enabled sites"
        description="Attendance views appear once an On-site administrator enables a site from Admin → Sites."
      />
    );
  }
  return <SiteCtx.Provider value={value}>{children}</SiteCtx.Provider>;
}

export function useSite(): SiteContextValue {
  const ctx = useContext(SiteCtx);
  if (!ctx) throw new Error("useSite must be used inside SiteProvider");
  return ctx;
}
