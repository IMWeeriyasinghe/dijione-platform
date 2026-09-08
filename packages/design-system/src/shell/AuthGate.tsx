"use client";

import { useQuery } from "@tanstack/react-query";
import { getAuthConfig, useAuth } from "@dijione/auth-client";
import { LoadingState } from "../ui/States";
import { DevPersonaSwitcher } from "./DevPersonaSwitcher";
import { EntraSignIn } from "./EntraSignIn";

export function AuthGate({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();

  // Which sign-in UI to render is a server decision (platform-api AUTH_MODE),
  // surfaced by /api/auth/config. Fetched only while signed out. `dev` is the
  // safe fallback if the config call fails — it is itself gated server-side
  // (the persona endpoints 404 unless AUTH_MODE=dev).
  const configQuery = useQuery({
    queryKey: ["auth-config"],
    queryFn: getAuthConfig,
    enabled: !user && !loading,
    staleTime: 5 * 60 * 1000,
  });

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <LoadingState label="Loading DijiOne…" />
      </div>
    );
  }

  if (!user) {
    if (configQuery.isLoading) {
      return (
        <div className="flex min-h-screen items-center justify-center">
          <LoadingState label="Loading DijiOne…" />
        </div>
      );
    }
    return configQuery.data?.auth_mode === "entra" ? <EntraSignIn /> : <DevPersonaSwitcher />;
  }

  return <>{children}</>;
}
