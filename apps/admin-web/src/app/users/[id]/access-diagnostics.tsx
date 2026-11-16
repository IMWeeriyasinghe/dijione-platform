"use client";

import { useQuery } from "@tanstack/react-query";
import type { AccessDiagnosticsOut } from "@dijione/contracts";
import { Card, ErrorState, formatDateTime, LoadingState } from "@dijione/design-system";
import { getAccessDiagnostics } from "@/lib/api";

const SOURCE_LABEL = { DIRECT: "Direct", GROUP: "Group", DEFAULT: "Default employee access" } as const;
const DEFAULT_STATE_LABEL = {
  GRANTED: "Granted",
  EXCLUDED: "Removed for this person",
  NOT_ELIGIBLE: "Not eligible",
  MODULE_DISABLED: "Application disabled",
} as const;
const LEVEL_MARK = { ok: "OK", info: "Note", warning: "Attention" } as const;

function Heading({ children }: { children: string }) {
  return <h3 className="text-sm font-semibold text-dt-text-primary">{children}</h3>;
}

function Chips({ items }: { items: string[] }) {
  if (items.length === 0) return <span className="text-sm text-dt-text-secondary">None</span>;
  return (
    <div className="flex flex-wrap gap-1.5">
      {items.map((p) => (
        <span key={p} className="rounded-full bg-dt-surface-warm px-2.5 py-0.5 text-xs text-dt-text-secondary">
          {p}
        </span>
      ))}
    </div>
  );
}

function Diagnostics({ d }: { d: AccessDiagnosticsOut }) {
  const a = d.account;
  return (
    <div className="space-y-6">
      <section aria-label="Checks" className="space-y-2">
        <Heading>What this means</Heading>
        <ul className="space-y-1.5">
          {d.checks.map((c) => (
            <li key={c.key} className="text-sm text-dt-text-secondary">
              <span className="mr-2 font-medium text-dt-text-primary">{LEVEL_MARK[c.level]}</span>
              {c.message}
            </li>
          ))}
        </ul>
      </section>

      <section aria-label="Account" className="space-y-2 border-t border-dt-border pt-4">
        <Heading>Account</Heading>
        <dl className="grid grid-cols-1 gap-x-6 gap-y-1 text-sm sm:grid-cols-2">
          <div><dt className="inline text-dt-text-secondary">Status: </dt><dd className="inline">{a.is_active ? "Active" : "Inactive"}</dd></div>
          <div><dt className="inline text-dt-text-secondary">Sign-in method: </dt><dd className="inline">{a.identity_provider}</dd></div>
          <div><dt className="inline text-dt-text-secondary">Microsoft link: </dt><dd className="inline">{a.entra_linked ? "Linked" : "Not linked yet"}</dd></div>
          <div><dt className="inline text-dt-text-secondary">Internal employee: </dt><dd className="inline">{a.internal_employee ? "Verified" : "Not verified"}</dd></div>
          <div><dt className="inline text-dt-text-secondary">Last sign-in: </dt><dd className="inline">{a.last_sign_in_at ? formatDateTime(a.last_sign_in_at) : "Never"}</dd></div>
          <div><dt className="inline text-dt-text-secondary">Platform role: </dt><dd className="inline">{a.platform_role}</dd></div>
        </dl>
        <div><p className="mb-1 text-sm text-dt-text-secondary">Platform permissions</p><Chips items={a.platform_permissions} /></div>
      </section>

      <section aria-label="Default access" className="space-y-2 border-t border-dt-border pt-4">
        <Heading>Default access</Heading>
        {d.default_access.length === 0 && <p className="text-sm text-dt-text-secondary">No application grants default access.</p>}
        {d.default_access.map((x) => (
          <div key={x.module_key} className="text-sm">
            <span className="font-medium text-dt-text-primary">{x.module_name}</span>{" "}
            <span className="text-dt-text-secondary">({x.role})</span>: {DEFAULT_STATE_LABEL[x.state]}
            {x.reasons.map((r) => (
              <p key={r} className="text-dt-text-secondary">{r}</p>
            ))}
          </div>
        ))}
      </section>

      <section aria-label="Groups" className="space-y-2 border-t border-dt-border pt-4">
        <Heading>Group membership</Heading>
        {d.groups.length === 0 && <p className="text-sm text-dt-text-secondary">Not a member of any group.</p>}
        {d.groups.map((g) => (
          <div key={g.group_id} className="text-sm">
            <span className="font-medium text-dt-text-primary">{g.group_name}</span>{" "}
            <span className="text-dt-text-secondary">({g.status === "ACTIVE" ? "active" : "inactive — grants do not apply"})</span>
            <ul className="ml-4 list-disc text-dt-text-secondary">
              {g.grants.map((x) => (
                <li key={`${x.module_key}-${x.role}`}>{x.module_key}: {x.role}{x.enabled ? "" : " (disabled)"}</li>
              ))}
              {g.grants.length === 0 && <li>No application grants</li>}
            </ul>
          </div>
        ))}
      </section>

      <section aria-label="Applications" className="space-y-4 border-t border-dt-border pt-4">
        <Heading>Application access</Heading>
        {d.modules.length === 0 && <p className="text-sm text-dt-text-secondary">No application access from any source.</p>}
        {d.modules.map((m) => (
          <div key={m.module_key} className="space-y-2" data-testid={`diag-module-${m.module_key}`}>
            <p className="text-sm font-medium text-dt-text-primary">
              {m.module_name} — {m.has_access ? m.role_name : "No effective access"}
            </p>
            <ul className="space-y-1 text-sm text-dt-text-secondary">
              {m.sources.map((s, i) => (
                <li key={i}>
                  {s.type === "GROUP" ? `Inherited from ${s.group_name}` : SOURCE_LABEL[s.type]} gives {s.role}
                  {" "}({s.permissions.length} permissions; client scope: {s.client_scope})
                </li>
              ))}
              {m.inactive.map((x, i) => (
                <li key={`i${i}`}>Not applied: {x.type === "DEFAULT" ? "default access " : ""}{x.group_name ? `${x.group_name} ` : ""}{x.role} — {x.reason}</li>
              ))}
            </ul>
            <p className="text-sm text-dt-text-secondary">
              {m.has_access && (
                <>Client scope: {m.client_scope.all_clients ? "All clients" : m.client_scope.client_names.join(", ") || "None"}. </>
              )}
              {m.scope_explanation}
            </p>
            {m.has_access && <Chips items={m.permissions} />}
          </div>
        ))}
      </section>

      <section aria-label="Session" className="space-y-1 border-t border-dt-border pt-4 text-sm">
        <Heading>Session</Heading>
        <p>Last sign-in: {d.session.last_sign_in_at ? formatDateTime(d.session.last_sign_in_at) : "Never"}</p>
        <p className="text-dt-text-secondary">Token freshness: unavailable. {d.session.token_issue_time_note}</p>
        {d.session.access_changes_since_last_sign_in !== null && (
          <p>
            Changes recorded since last sign-in: {d.session.access_changes_since_last_sign_in}
            {d.session.latest_access_change_at ? ` (latest ${formatDateTime(d.session.latest_access_change_at)})` : ""}
          </p>
        )}
        <p className="text-dt-text-secondary">
          Session lifetime: {Math.round(d.session.token_lifetime_minutes / 60)} hours. Changes take effect at the next sign-in or refresh.
        </p>
      </section>
    </div>
  );
}

export function AccessDiagnostics({ userId }: { userId: number }) {
  const query = useQuery({
    queryKey: ["admin", "users", userId, "access-diagnostics"],
    queryFn: () => getAccessDiagnostics(userId),
  });
  return (
    <Card className="p-5">
      {query.isLoading && <LoadingState label="Running access diagnostics…" />}
      {query.isError && <ErrorState message="Could not load access diagnostics." />}
      {query.data && <Diagnostics d={query.data} />}
    </Card>
  );
}
