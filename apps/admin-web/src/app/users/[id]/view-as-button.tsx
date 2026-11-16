"use client";

import type { AdminUserOut, EffectiveAccessOut } from "@dijione/contracts";
import { ApiError, startViewAs, useOptionalAuth } from "@dijione/auth-client";
import { Button, Modal } from "@dijione/design-system";
import { Eye } from "lucide-react";
import { useState } from "react";

/**
 * "View as": opens a read-only session that shows this employee's applications exactly as they see
 * them. Offered only to a Super Admin holding platform.admin.view_as; the server decides again, and
 * only for an active internal employee other than oneself.
 */
export function ViewAsButton({ user, effective }: { user: AdminUserOut; effective: EffectiveAccessOut | undefined }) {
  const me = useOptionalAuth()?.user ?? null;
  const permitted = me?.platform_permissions.includes("platform.admin.view_as") ?? false;
  const [open, setOpen] = useState(false);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!me || !permitted || me.platform_role !== "SUPER_ADMIN" || me.id === user.id || !user.is_active) return null;

  async function start() {
    setStarting(true);
    setError(null);
    try {
      await startViewAs(user.id, window.location.pathname + window.location.search);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not start the View as session.");
      setStarting(false);
    }
  }

  const modules = effective?.modules ?? [];
  // Older platform-api answers carry no eligibility field: then the server alone decides.
  const eligible = user.eligible_employee !== false;
  const reason = !user.directory_verified
    ? "Verify this profile with the directory to enable View as. Their access can still be previewed here."
    : "Not matched to a BambooHR employee record, so View as is not available until HR reconciliation. Their access can still be previewed here.";
  return (
    <>
      <Button size="sm" variant="secondary" onClick={() => setOpen(true)}>
        <Eye className="mr-1.5 size-4" /> {eligible ? "View as" : "Preview access"}
      </Button>
      <Modal open={open} onClose={() => (starting ? undefined : setOpen(false))} title={`View as ${user.full_name}`}>
        <div className="flex flex-col gap-4">
          <p className="text-sm text-dt-text-secondary">
            You will see DijiOne exactly as {user.full_name} does, with only their access. The session is read-only: nothing
            you do can change data, send messages or approve anything. It lasts 30 minutes, ends if their access changes,
            and its start, end and every blocked attempt are recorded.
          </p>
          <div>
            <p className="mb-2 text-sm font-medium text-dt-text-primary">What they can access</p>
            {modules.length === 0 ? (
              <p className="text-sm text-dt-text-secondary">No application access: you would see an empty home page.</p>
            ) : (
              <ul className="space-y-2" data-testid="view-as-access">
                {modules.map((m) => (
                  <li key={m.module_key} className="rounded-lg border border-dt-border p-3 text-sm">
                    <span className="font-medium text-dt-text-primary">{m.module_name}</span>
                    <span className="text-dt-text-secondary"> as {m.role_name}</span>
                    <p className="mt-1 text-dt-text-secondary">
                      {m.permissions.length} permissions. Client scope:{" "}
                      {m.client_scope.all_clients ? "all clients" : m.client_scope.client_names.join(", ") || "none"}.
                    </p>
                  </li>
                ))}
              </ul>
            )}
          </div>
          {!eligible && (
            <p className="text-sm text-dt-text-secondary" data-testid="view-as-preview-only">
              {reason}
            </p>
          )}
          {error && <p className="text-sm text-dt-danger">{error}</p>}
          <div className="flex justify-end gap-2">
            <Button variant="secondary" onClick={() => setOpen(false)} disabled={starting}>
              Cancel
            </Button>
            <Button onClick={() => void start()} loading={starting} disabled={!eligible}>
              Start read-only session
            </Button>
          </div>
        </div>
      </Modal>
    </>
  );
}
