"use client";

import { useAuth } from "@/lib/auth-context";
import { LoadingState } from "@/components/ui/States";
import { DevPersonaSwitcher } from "./DevPersonaSwitcher";

export function AuthGate({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <LoadingState label="Loading DijiOne…" />
      </div>
    );
  }

  if (!user) return <DevPersonaSwitcher />;

  return <>{children}</>;
}
