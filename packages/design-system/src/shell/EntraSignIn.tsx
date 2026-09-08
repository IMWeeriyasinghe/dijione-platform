"use client";

import Image from "next/image";
import { LogIn } from "lucide-react";
import { beginEntraLogin } from "@dijione/auth-client";
import { Button } from "../ui/Button";

/**
 * Unauthenticated entry point when the environment runs real Microsoft Entra
 * ID sign-in (platform-api `AUTH_MODE=entra`, reported by `/api/auth/config`).
 *
 * The Dev Identity Mode persona switcher is NOT shown here — it is disabled
 * server-side (`/api/auth/dev-*` -> 404). The button navigates to shell-web's
 * `/login` route, which builds the authorize URL + PKCE flow cookie and 302s
 * to Microsoft; `/api/auth/callback` completes the exchange.
 */
export function EntraSignIn() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-linear-to-br from-dt-red-deep via-dt-red to-dt-burnt-orange px-4 py-12">
      <div className="w-full max-w-md rounded-3xl border border-white/10 bg-dt-surface p-8 text-center shadow-2xl sm:p-10">
        {/* unoptimized: see Sidebar.tsx's identical logo usage. */}
        <Image
          src="/brand/dijital-team-logo.png"
          alt="Dijital Team"
          width={180}
          height={48}
          priority
          unoptimized
          className="mx-auto mb-6 h-10 w-auto"
        />
        <h1 className="text-2xl font-semibold text-dt-text-primary">Welcome to DijiOne</h1>
        <p className="mt-1 text-sm text-dt-text-secondary">
          The unified digital operating workspace for Dijital Team.
        </p>

        <Button
          type="button"
          onClick={() => beginEntraLogin()}
          className="mt-8 w-full justify-center gap-2"
        >
          <LogIn className="size-4" />
          Sign in with Microsoft
        </Button>

        <p className="mt-4 text-xs text-dt-text-secondary">
          You&apos;ll be redirected to Microsoft to sign in with your Dijital Team account.
        </p>
      </div>
      <p className="mt-6 text-center text-xs text-white/70">
        New accounts are created inactive — a platform administrator activates
        them and assigns access.
      </p>
    </div>
  );
}
