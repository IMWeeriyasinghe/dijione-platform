"use client";

import { BrandLogo } from "@dijione/design-system";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { redeemToken, useExternalAuth } from "@/lib/external-auth";

type Phase = "working" | "error";

export default function AccessPage() {
  const router = useRouter();
  const { establish } = useExternalAuth();
  const [phase, setPhase] = useState<Phase>("working");
  const ran = useRef(false);

  useEffect(() => {
    if (ran.current) return;
    ran.current = true;

    // The raw token arrives in the URL fragment only — never a query
    // string, so it is never sent to the server as part of this
    // navigation and never lands in an access log.
    const raw = window.location.hash.replace(/^#/, "").trim();
    // Clear the fragment immediately, before any await, so it does not
    // linger in the address bar / browser history.
    window.history.replaceState(null, "", window.location.pathname);

    void (async () => {
      const session = raw ? await redeemToken(raw) : null;
      if (session && raw) {
        establish(session, raw);
        router.replace("/");
      } else {
        setPhase("error");
      }
    })();
  }, [establish, router]);

  return (
    <div className="flex min-h-screen items-center justify-center bg-dt-background px-4">
      <div className="w-full max-w-md rounded-2xl border border-dt-border bg-dt-surface p-8 text-center shadow-sm">
        <BrandLogo width={150} className="mx-auto mb-5" />
        <p className="text-xs font-semibold uppercase tracking-wide text-dt-orange">
          Client Talent Review Workspace
        </p>
        {phase === "working" ? (
          <>
            <h1 className="mt-2 text-xl font-semibold text-dt-text-primary">Opening your workspace…</h1>
            <p className="mt-2 text-sm text-dt-text-secondary">One moment.</p>
          </>
        ) : (
          <>
            <h1 className="mt-2 text-xl font-semibold text-dt-text-primary">
              This access link is invalid or has expired
            </h1>
            <p className="mt-2 text-sm text-dt-text-secondary">
              Ask your Dijital Team contact to send you a new link.
            </p>
          </>
        )}
      </div>
    </div>
  );
}
