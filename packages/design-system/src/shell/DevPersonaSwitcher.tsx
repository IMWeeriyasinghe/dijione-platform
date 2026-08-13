"use client";

import { useQuery } from "@tanstack/react-query";
import Image from "next/image";
import { useState } from "react";
import { listDevPersonas } from "@dijione/auth-client";
import { useAuth } from "@dijione/auth-client";
import { Avatar } from "../ui/Avatar";
import { LoadingState, ErrorState } from "../ui/States";
import { ShieldCheck } from "lucide-react";

export function DevPersonaSwitcher() {
  const { login } = useAuth();
  const [pending, setPending] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { data: personas, isLoading, isError, refetch } = useQuery({
    queryKey: ["dev-personas"],
    queryFn: listDevPersonas,
  });

  async function handleSelect(personaKey: string) {
    setPending(personaKey);
    setError(null);
    try {
      await login(personaKey);
    } catch {
      setError("Could not sign in as this persona. Please try again.");
    } finally {
      setPending(null);
    }
  }

  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-linear-to-br from-dt-red-deep via-dt-red to-dt-burnt-orange px-4 py-12">
      <div className="w-full max-w-2xl rounded-3xl border border-white/10 bg-dt-surface p-8 shadow-2xl sm:p-10">
        <div className="mb-8 flex flex-col items-center text-center">
          {/* unoptimized: see Sidebar.tsx's identical logo usage. */}
          <Image
            src="/brand/dijital-team-logo.png"
            alt="Dijital Team"
            width={180}
            height={48}
            priority
            unoptimized
            className="mb-6 h-10 w-auto"
          />
          <h1 className="text-2xl font-semibold text-dt-text-primary">Welcome to DijiOne</h1>
          <p className="mt-1 text-sm text-dt-text-secondary">
            The unified digital operating workspace for Dijital Team.
          </p>
          <div className="mt-4 flex items-center gap-1.5 rounded-full border border-dt-border bg-dt-surface-warm px-3 py-1 text-xs font-medium text-dt-text-secondary">
            <ShieldCheck className="size-3.5 text-dt-burnt-orange" />
            Dev Identity Mode — local &amp; demo use only
          </div>
        </div>

        {isLoading && <LoadingState label="Loading personas…" />}
        {isError && <ErrorState message="Could not load personas from the API." onRetry={() => refetch()} />}
        {error && <p className="mb-4 text-center text-sm text-dt-danger">{error}</p>}

        {personas && (
          <div className="grid gap-3 sm:grid-cols-2">
            {personas.map((p) => (
              <button
                key={p.persona_key}
                onClick={() => handleSelect(p.persona_key)}
                disabled={pending !== null}
                className="flex items-center gap-3 rounded-xl border border-dt-border bg-dt-surface-warm p-4 text-left transition hover:border-dt-orange hover:bg-dt-cream disabled:opacity-60"
              >
                <Avatar name={p.full_name} color={p.avatar_color} />
                <div className="min-w-0">
                  <p className="truncate text-sm font-semibold text-dt-text-primary">{p.full_name}</p>
                  <p className="truncate text-xs text-dt-text-secondary">{p.title ?? "—"}</p>
                </div>
                {pending === p.persona_key && (
                  <span className="ml-auto text-xs text-dt-burnt-orange">Signing in…</span>
                )}
              </button>
            ))}
          </div>
        )}
      </div>
      <p className="mt-6 text-center text-xs text-white/70">
        Production sign-in will use Microsoft Entra ID Single Sign-On.
      </p>
    </div>
  );
}
