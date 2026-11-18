"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useAuth, usePlatformPermission } from "@dijione/auth-client";
import type { AdminUserOut, ApplicationDetailOut } from "@dijione/contracts";
import { Button, Card, ClientScopePicker, FormField, Input, Modal, Select, Table, Td, Th, Thead, Tr } from "@dijione/design-system";
import {
  ApiError,
  appointApplicationAdministrator,
  liftApplicationSuspension,
  listApplicationAdministrators,
  listApplicationSuspensions,
  removeApplicationAdministrator,
  setModuleEnabled,
} from "@/lib/api";

const message = (e: unknown, fallback: string) => (e instanceof ApiError ? e.message : fallback);

/** Central Admin's part of delegated application access: who administers access to this
 * application (Super Admin appoints, with explicit authority), current application suspensions
 * (central override), and the application's on/off switch. */
export function DelegatedAccessSection({
  app,
  users,
  clients,
}: {
  app: ApplicationDetailOut;
  users: AdminUserOut[];
  clients: { id: number; name: string }[];
}) {
  const moduleKey = app.module_key;
  const queryClient = useQueryClient();
  const canAppoint = usePlatformPermission("platform.admin.manage_admins");
  const canLift = usePlatformPermission("platform.admin.manage_users");
  const canToggle = usePlatformPermission("platform.admin.manage_modules");
  const { user: me } = useAuth();
  const admins = useQuery({ queryKey: ["admin", "applications", moduleKey, "administrators"], queryFn: () => listApplicationAdministrators(moduleKey) });
  const suspensions = useQuery({ queryKey: ["admin", "applications", moduleKey, "suspensions"], queryFn: () => listApplicationSuspensions(moduleKey) });
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["admin", "applications", moduleKey] });
  const [appointing, setAppointing] = useState(false);
  const remove = useMutation({
    mutationFn: ({ userId, reason }: { userId: number; reason?: string }) => removeApplicationAdministrator(moduleKey, userId, reason),
    onSuccess: refresh,
  });
  const lift = useMutation({ mutationFn: (userId: number) => liftApplicationSuspension(moduleKey, userId), onSuccess: refresh });
  const toggle = useMutation({
    mutationFn: () => setModuleEnabled(moduleKey, !app.enabled),
    onSuccess: () => {
      refresh();
      queryClient.invalidateQueries({ queryKey: ["admin", "modules"] });
    },
  });

  return (
    <section aria-labelledby="delegated-access" className="mt-10 space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 id="delegated-access" className="text-sm font-semibold uppercase tracking-wide text-dt-text-secondary">
          Application Access Administration
        </h2>
        {canToggle && (
          <Button
            size="sm"
            variant={app.enabled ? "danger" : "primary"}
            loading={toggle.isPending}
            onClick={() => {
              if (!app.enabled || window.confirm(`Disable ${app.module_name}? Everyone loses access to it at their next request.`)) {
                toggle.mutate();
              }
            }}
          >
            {app.enabled ? "Disable application" : "Enable application"}
          </Button>
        )}
      </div>
      {toggle.isError && <p role="alert" className="text-sm text-dt-danger">{message(toggle.error, "Could not change the application.")}</p>}

      {app.delegation_supported && (
        <div>
          <div className="mb-3 flex items-center justify-between">
            <p className="text-sm font-medium text-dt-text-primary">Application Administrators</p>
            {canAppoint && (
              <Button size="sm" onClick={() => setAppointing(true)} disabled={!app.enabled}>
                Appoint administrator
              </Button>
            )}
          </div>
          {remove.isError && <p role="alert" className="mb-2 text-sm text-dt-danger">{message(remove.error, "Could not remove.")}</p>}
          {!admins.data?.length ? (
            <Card className="p-5 text-sm text-dt-text-secondary">
              No access administrators. Until one is appointed, access to this application is managed here only.
            </Card>
          ) : (
            <Table>
              <Thead>
                <tr>
                  <Th>Administrator</Th>
                  <Th>May grant</Th>
                  {app.supports_client_scope !== false && <Th>Client authority</Th>}
                  <Th>Appointed by</Th>
                  <Th><span className="sr-only">Actions</span></Th>
                </tr>
              </Thead>
              <tbody>
                {admins.data.map((a) => (
                  <Tr key={a.user_id}>
                    <Td>
                      <p className="font-medium text-dt-text-primary">{a.full_name}</p>
                      <p className="text-xs text-dt-text-secondary">{a.email}</p>
                      {!a.eligible_employee && <p className="text-xs text-dt-warning">Not currently eligible: the appointment grants nothing.</p>}
                    </Td>
                    <Td className="text-sm text-dt-text-secondary">{a.grantable_roles.map((r) => r.name).join(", ")}</Td>
                    {app.supports_client_scope !== false && (
                      <Td className="text-sm text-dt-text-secondary">
                        {a.client_authority?.all_clients ? "All clients" : a.client_authority?.clients.map((c) => c.name).join(", ")}
                      </Td>
                    )}
                    <Td className="text-sm text-dt-text-secondary">{a.appointed_by_name ?? "—"}</Td>
                    <Td className="text-right">
                      {canAppoint && (
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => {
                            const self = a.user_id === me?.id;
                            const reason = self ? window.prompt("Break-glass: why are you changing your own access?") ?? undefined : undefined;
                            if (self && !reason) return;
                            if (admins.data.length === 1 && !window.confirm("This is the last administrator of this application. Remove?")) return;
                            remove.mutate({ userId: a.user_id, reason });
                          }}
                        >
                          Remove
                        </Button>
                      )}
                    </Td>
                  </Tr>
                ))}
              </tbody>
            </Table>
          )}
        </div>
      )}

      {app.delegation_supported && (
        <div>
          <p className="mb-3 text-sm font-medium text-dt-text-primary">Suspended in this application</p>
          {lift.isError && <p role="alert" className="mb-2 text-sm text-dt-danger">{message(lift.error, "Could not lift.")}</p>}
          {!suspensions.data?.length ? (
            <Card className="p-5 text-sm text-dt-text-secondary">Nobody is suspended.</Card>
          ) : (
            <Table>
              <Thead>
                <tr>
                  <Th>Person</Th>
                  <Th>Reason</Th>
                  <Th>By</Th>
                  <Th><span className="sr-only">Actions</span></Th>
                </tr>
              </Thead>
              <tbody>
                {suspensions.data.map((s) => (
                  <Tr key={s.user_id}>
                    <Td>
                      <p className="font-medium text-dt-text-primary">{s.full_name}</p>
                      <p className="text-xs text-dt-text-secondary">{s.email}</p>
                    </Td>
                    <Td className="text-sm text-dt-text-secondary">{s.reason || "—"}</Td>
                    <Td className="text-sm text-dt-text-secondary">{s.suspended_by_name ?? "—"}</Td>
                    <Td className="text-right">
                      {canLift && (
                        <Button size="sm" variant="ghost" loading={lift.isPending} onClick={() => lift.mutate(s.user_id)}>
                          Lift suspension
                        </Button>
                      )}
                    </Td>
                  </Tr>
                ))}
              </tbody>
            </Table>
          )}
        </div>
      )}

      {appointing && (
        <AppointModal
          app={app}
          users={users.filter((u) => u.eligible_employee && !admins.data?.some((a) => a.user_id === u.id))}
          clients={clients}
          meId={me?.id}
          onClose={() => setAppointing(false)}
          onDone={refresh}
        />
      )}
    </section>
  );
}

function AppointModal({
  app,
  users,
  clients,
  meId,
  onClose,
  onDone,
}: {
  app: ApplicationDetailOut;
  users: AdminUserOut[];
  clients: { id: number; name: string }[];
  meId?: number;
  onClose: () => void;
  onDone: () => void;
}) {
  const [userId, setUserId] = useState<number | "">("");
  const [roles, setRoles] = useState<string[]>([]);
  const [scope, setScope] = useState({ all_clients: false, client_ids: [] as number[] });
  const [reason, setReason] = useState("");
  const scoped = app.supports_client_scope !== false;
  const self = userId === meId;
  const save = useMutation({
    mutationFn: () =>
      appointApplicationAdministrator(app.module_key, Number(userId), {
        grantable_roles: roles,
        ...(scoped ? { client_authority: scope } : {}),
        ...(self ? { break_glass_reason: reason } : {}),
      }),
    onSuccess: () => {
      onDone();
      onClose();
    },
  });
  const invalid = userId === "" || roles.length === 0 || (scoped && !scope.all_clients && scope.client_ids.length === 0) || (self && reason.trim().length < 10);
  return (
    <Modal open onClose={onClose} title={`Appoint ${app.module_name} administrator`}>
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate();
        }}
      >
        <FormField label="Employee" htmlFor="appoint-user" hint="Only active, verified employees matched to an HR record">
          <Select id="appoint-user" value={userId} onChange={(e) => setUserId(e.target.value ? Number(e.target.value) : "")}>
            <option value="">Choose…</option>
            {users.map((u) => (
              <option key={u.id} value={u.id}>
                {u.full_name} ({u.email})
              </option>
            ))}
          </Select>
        </FormField>
        <fieldset className="space-y-1">
          <legend className="text-sm font-medium text-dt-text-primary">May grant</legend>
          {(app.delegable_roles ?? []).map((r) => (
            <label key={r.key} className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={roles.includes(r.key)}
                onChange={(e) => setRoles(e.target.checked ? [...roles, r.key] : roles.filter((k) => k !== r.key))}
              />
              {r.name}
            </label>
          ))}
        </fieldset>
        {scoped && (
          <ClientScopePicker authority={{ all_clients: true, clients: [] }} allClientNames={clients} value={scope} onChange={setScope} />
        )}
        {self && (
          <FormField label="Break-glass reason (you are appointing yourself)" htmlFor="appoint-reason" hint="At least 10 characters; other Super Admins are notified">
            <Input id="appoint-reason" value={reason} onChange={(e) => setReason(e.target.value)} />
          </FormField>
        )}
        {save.isError && <p role="alert" className="text-sm text-dt-danger">{message(save.error, "Could not appoint.")}</p>}
        <div className="flex justify-end gap-2">
          <Button type="button" variant="ghost" onClick={onClose}>Cancel</Button>
          <Button type="submit" loading={save.isPending} disabled={invalid}>Appoint</Button>
        </div>
      </form>
    </Modal>
  );
}
