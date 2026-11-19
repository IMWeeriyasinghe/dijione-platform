"use client";

import { ChevronDown, ShieldCheck } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";
import { useAuth } from "@dijione/auth-client";
import type { AccessGrantSummary, CurrentUser } from "@dijione/contracts";

/** Where the header is: DijiOne Home / Central Admin ("platform") or one application (its module key). */
export type RoleContext = "platform" | string;

const SOURCE_LABEL: Record<AccessGrantSummary["source"], string> = {
  DIRECT: "Assigned directly",
  GROUP: "From group",
  BASELINE: "Every employee",
  APPOINTMENT: "Appointed",
};

type Summary = {
  primary: string;
  extra: number;
  business: AccessGrantSummary[];
  administrative: AccessGrantSummary[];
  scope: string | null;
};

/** What the header shows for the current context. Pure, from the signed-in user's /me data:
 * nothing is re-derived here, and a platform role is never shown inside an application. */
export function summarizeRoles(user: CurrentUser, context: RoleContext): Summary | null {
  if (context === "platform") {
    return { primary: user.platform_role_name ?? user.platform_role, extra: 0, business: [], administrative: [], scope: null };
  }
  const entry = user.module_roles.find((r) => r.module_key === context);
  if (!entry) return null;
  const grants = entry.grants ?? [];
  const business = grants.filter((g) => !g.administrative);
  const administrative = grants.filter((g) => g.administrative);
  const distinct = new Set(grants.map((g) => g.role));
  const scope = entry.client_scope
    ? entry.client_scope.all_clients
      ? "All clients"
      : entry.client_scope.clients.join(", ") || "No clients"
    : null;
  return {
    primary: entry.role_name ?? entry.role,
    extra: Math.max(0, distinct.size - 1),
    business,
    administrative,
    scope,
  };
}

/** Compact, read-only role indicator next to the profile picture, with an expandable access summary.
 * It changes nothing: there is no role switching here. */
export function RoleIndicator({ context }: { context: RoleContext }) {
  const { user } = useAuth();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const panelId = useId();

  useEffect(() => {
    if (!open) return;
    const onClick = (e: MouseEvent) => ref.current && !ref.current.contains(e.target as Node) && setOpen(false);
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  if (!user) return null;
  const s = summarizeRoles(user, context);
  if (!s) return null;

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-controls={panelId}
        aria-label={`Your role: ${s.primary}${s.extra ? ` and ${s.extra} more` : ""}. Show access summary`}
        className="flex max-w-[7.5rem] items-center gap-1 rounded-full border border-dt-border bg-dt-surface-warm px-2.5 py-1 text-xs font-medium text-dt-text-primary transition hover:border-dt-burnt-orange focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-dt-orange sm:max-w-[16rem]"
      >
        <span className="truncate">{s.primary}</span>
        {s.extra > 0 && <span className="shrink-0 rounded-full bg-dt-cream px-1.5 text-dt-burnt-orange">+{s.extra}</span>}
        <ChevronDown className="size-3 shrink-0 text-dt-text-secondary" aria-hidden />
      </button>
      {open && (
        <div
          id={panelId}
          role="dialog"
          aria-label="Your access"
          className="absolute right-0 z-40 mt-2 w-72 max-w-[calc(100vw-2rem)] rounded-2xl border border-dt-border bg-dt-surface p-3 text-sm shadow-xl"
        >
          {context === "platform" ? (
            <p className="text-dt-text-primary">
              DijiOne role: <strong>{s.primary}</strong>
            </p>
          ) : (
            <>
              <p className="text-xs font-semibold uppercase tracking-wide text-dt-text-secondary">Your roles here</p>
              <ul className="mt-1 space-y-1">
                {s.business.map((g, i) => (
                  <li key={`b${i}`} className="flex flex-wrap items-baseline justify-between gap-x-2">
                    <span className="font-medium text-dt-text-primary">{g.role_name}</span>
                    <span className="text-xs text-dt-text-secondary">
                      {SOURCE_LABEL[g.source]}
                      {g.group_name ? `: ${g.group_name}` : ""}
                      {g.mandatory ? " (mandatory)" : ""}
                    </span>
                  </li>
                ))}
                {s.business.length === 0 && <li className="text-xs text-dt-text-secondary">No business role in this application.</li>}
              </ul>
              {s.scope && <p className="mt-2 text-xs text-dt-text-secondary">Clients: {s.scope}</p>}
              {s.administrative.length > 0 && (
                <div className="mt-3 border-t border-dt-border pt-2">
                  <p className="flex items-center gap-1 text-xs font-semibold uppercase tracking-wide text-dt-text-secondary">
                    <ShieldCheck className="size-3.5" aria-hidden /> Administration
                  </p>
                  {s.administrative.map((g, i) => (
                    <p key={`a${i}`} className="mt-1 text-dt-text-primary">
                      {g.role_name} <span className="text-xs text-dt-text-secondary">(manages access; no business permissions)</span>
                    </p>
                  ))}
                </div>
              )}
            </>
          )}
          <p className="mt-3 text-xs text-dt-text-secondary">Read only. Ask an administrator to change your access.</p>
        </div>
      )}
    </div>
  );
}
