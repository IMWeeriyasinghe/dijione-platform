"use client";

import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ShieldCheck, UserPlus, Users } from "lucide-react";
import { ApiError, accessApi } from "@dijione/auth-client";
import type {
  AccessClientScopeIn,
  AccessMe,
  AccessPerson,
  AccessScope,
  AccessSource,
  AppUser,
} from "@dijione/contracts";

import { Button } from "../ui/Button";
import { Card, CardContent } from "../ui/Card";
import { FormField, Input, Select, Textarea } from "../ui/FormField";
import { Modal } from "../ui/Modal";
import { PageHeader } from "../ui/PageHeader";
import { EmptyState, ErrorState, LoadingState } from "../ui/States";
import { Table, Td, Th, Thead, Tr } from "../ui/Table";

/** An application's Management → Access page. The same component in every application; each
 * passes its own module key. Platform Core decides everything (who is an administrator, what they
 * may grant, which clients); this page only presents it. */
export function AccessManagementPage({ moduleKey, appName }: { moduleKey: string; appName: string }) {
  const api = useMemo(() => accessApi(moduleKey), [moduleKey]);
  const me = useQuery({ queryKey: ["access", moduleKey, "me"], queryFn: api.me, retry: false });
  const [tab, setTab] = useState<"people" | "admins">("people");

  if (me.isLoading) return <LoadingState label="Loading access management…" />;
  if (me.isError) return <ErrorState message={explain(me.error, "Access management could not be loaded.")} onRetry={() => me.refetch()} />;
  if (!me.data?.is_admin) {
    return (
      <EmptyState
        icon={ShieldCheck}
        title="You are not an access administrator"
        description={`Only people appointed by a Super Admin can manage access to ${appName}.`}
      />
    );
  }
  return (
    <div>
      <PageHeader
        title="Access"
        description={`Who can use ${appName}, and with which role. Changes apply at the person's next request.`}
      />
      <div role="tablist" aria-label="Access sections" className="mb-4 flex gap-2">
        <TabButton active={tab === "people"} onClick={() => setTab("people")} icon={<Users size={16} />}>
          People
        </TabButton>
        <TabButton active={tab === "admins"} onClick={() => setTab("admins")} icon={<ShieldCheck size={16} />}>
          Administrators
        </TabButton>
      </div>
      {tab === "people" ? <PeopleTab moduleKey={moduleKey} me={me.data} /> : <AdminsTab moduleKey={moduleKey} />}
    </div>
  );
}

function TabButton(props: { active: boolean; onClick: () => void; icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <button
      role="tab"
      aria-selected={props.active}
      onClick={props.onClick}
      className={
        "inline-flex items-center gap-2 rounded-xl px-3 py-1.5 text-sm font-medium focus-visible:outline-none " +
        "focus-visible:ring-2 focus-visible:ring-dt-orange " +
        (props.active ? "bg-dt-cream text-dt-text-primary" : "text-dt-text-secondary hover:bg-dt-surface-warm")
      }
    >
      {props.icon}
      {props.children}
    </button>
  );
}

export function explain(error: unknown, fallback: string): string {
  if (error instanceof ApiError) {
    if (error.status === 404) return "Access management is not available for this application in this environment.";
    if (error.status === 403 && /View-as/i.test(error.message)) return "Not available in a read-only View-as session.";
    return error.message || fallback;
  }
  return fallback;
}

// --- People ----------------------------------------------------------------------------------

function PeopleTab({ moduleKey, me }: { moduleKey: string; me: AccessMe }) {
  const api = useMemo(() => accessApi(moduleKey), [moduleKey]);
  const users = useQuery({ queryKey: ["access", moduleKey, "users"], queryFn: api.users });
  const [adding, setAdding] = useState(false);
  const [editing, setEditing] = useState<AppUser | null>(null);
  const [removing, setRemoving] = useState<AppUser | null>(null);
  const queryClient = useQueryClient();
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["access", moduleKey] });
  const lift = useMutation({ mutationFn: (userId: number) => api.liftSuspension(userId), onSuccess: refresh });

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-dt-text-secondary">
          You may grant: {me.grantable_roles.map((r) => r.name).join(", ") || "no roles"}
          {me.client_authority && <> · Clients: {scopeText(me.client_authority)}</>}
        </p>
        <Button onClick={() => setAdding(true)}>
          <UserPlus size={16} /> Add person
        </Button>
      </div>
      {users.data?.default_access_note && (
        <p className="rounded-xl border border-dt-border bg-dt-surface-warm px-4 py-3 text-sm text-dt-text-secondary">
          {users.data.default_access_note}
        </p>
      )}
      {lift.isError && <p role="alert" className="text-sm text-dt-danger">{explain(lift.error, "Could not restore access.")}</p>}
      <Card>
        <CardContent className="p-0">
          {users.isLoading ? (
            <LoadingState />
          ) : users.isError ? (
            <ErrorState message={explain(users.error, "People could not be loaded.")} onRetry={() => users.refetch()} />
          ) : !users.data?.users.length ? (
            <EmptyState title="Nobody has been given access here yet" description="Use Add person to grant access." />
          ) : (
            <Table>
              <Thead>
                <Tr>
                  <Th>Person</Th>
                  <Th>Access</Th>
                  <Th>From</Th>
                  <Th className="text-right">Actions</Th>
                </Tr>
              </Thead>
              <tbody>
                {users.data.users.map((u) => (
                  <Tr key={u.user_id}>
                    <Td>
                      <div className="font-medium text-dt-text-primary">{u.full_name}</div>
                      <div className="text-xs text-dt-text-secondary">{u.email}</div>
                    </Td>
                    <Td>{u.has_access ? u.role_name : <span className="text-dt-text-secondary">No access</span>}</Td>
                    <Td>
                      <Sources sources={u.sources} suspended={Boolean(u.suspension)} />
                      {u.suspension && (
                        <div className="mt-1 text-xs text-dt-warning">
                          Suspended here by {u.suspension.suspended_by_name ?? "an administrator"}
                          {u.suspension.reason && <>: {u.suspension.reason}</>}
                        </div>
                      )}
                    </Td>
                    <Td className="text-right">
                      {u.manageable ? (
                        <div className="flex flex-wrap justify-end gap-2">
                          <Button size="sm" variant="secondary" onClick={() => setEditing(u)}>
                            {u.has_access && u.sources.some((s) => s.type === "DIRECT") ? "Change" : "Grant"}
                          </Button>
                          {u.suspension ? (
                            <Button size="sm" variant="ghost" loading={lift.isPending} onClick={() => lift.mutate(u.user_id)}>
                              Restore group access
                            </Button>
                          ) : (
                            <Button size="sm" variant="ghost" onClick={() => setRemoving(u)}>
                              Remove
                            </Button>
                          )}
                        </div>
                      ) : (
                        <span className="text-xs text-dt-text-secondary">{u.managed_reason}</span>
                      )}
                    </Td>
                  </Tr>
                ))}
              </tbody>
            </Table>
          )}
        </CardContent>
      </Card>
      {adding && <AddPersonDialog moduleKey={moduleKey} me={me} onClose={() => setAdding(false)} onDone={refresh} />}
      {editing && (
        <GrantDialog
          moduleKey={moduleKey}
          me={me}
          person={{ name: editing.full_name, userId: editing.user_id }}
          current={editing.sources.find((s) => s.type === "DIRECT")}
          onClose={() => setEditing(null)}
          onDone={refresh}
        />
      )}
      {removing && <RemoveDialog moduleKey={moduleKey} user={removing} onClose={() => setRemoving(null)} onDone={refresh} />}
    </div>
  );
}

const SOURCE_LABEL: Record<AccessSource["type"], string> = {
  DIRECT: "Granted here",
  GROUP: "Group",
  BASELINE: "Every employee",
  APPOINTMENT: "Administrator",
};

export function Sources({ sources, suspended }: { sources: AccessSource[]; suspended?: boolean }) {
  if (!sources.length) return <span className="text-xs text-dt-text-secondary">—</span>;
  return (
    <ul className="flex flex-wrap gap-1.5" aria-label="Access sources">
      {sources.map((s, i) => (
        <li
          key={`${s.type}-${s.group_id ?? i}`}
          title={s.mandated ? "Mandatory: cannot be removed here" : undefined}
          className={
            "rounded-full border px-2 py-0.5 text-xs " +
            (!s.applies
              ? "border-dt-border text-dt-text-secondary line-through"
              : s.mandated
                ? "border-dt-border bg-dt-surface-warm text-dt-text-primary"
                : "border-dt-border text-dt-text-primary")
          }
        >
          {SOURCE_LABEL[s.type]}
          {s.group_name && `: ${s.group_name}`} · {s.role_name}
          {s.mandated && " (mandatory)"}
          {!s.applies && suspended && " (suspended)"}
        </li>
      ))}
    </ul>
  );
}

function scopeText(scope: AccessScope): string {
  return scope.all_clients ? "All clients" : scope.clients.map((c) => c.name).join(", ") || "none";
}

/** Clients within the administrator's authority. "All clients" is offered only when the authority
 * itself is all clients. */
export function ClientScopePicker({
  authority,
  value,
  onChange,
  allClientNames,
}: {
  authority: AccessScope;
  value: AccessClientScopeIn;
  onChange: (v: AccessClientScopeIn) => void;
  allClientNames?: { id: number; name: string }[];
}) {
  const choices = authority.all_clients ? allClientNames ?? [] : authority.clients;
  return (
    <fieldset className="space-y-2">
      <legend className="text-sm font-medium text-dt-text-primary">Clients</legend>
      {authority.all_clients && (
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={value.all_clients}
            onChange={(e) => onChange({ all_clients: e.target.checked, client_ids: [] })}
          />
          All clients
        </label>
      )}
      {!value.all_clients && (
        <div className="max-h-48 space-y-1 overflow-y-auto rounded-xl border border-dt-border p-2">
          {choices.length === 0 && <p className="text-xs text-dt-text-secondary">No clients available.</p>}
          {choices.map((c) => (
            <label key={c.id} className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={value.client_ids.includes(c.id)}
                onChange={(e) =>
                  onChange({
                    all_clients: false,
                    client_ids: e.target.checked ? [...value.client_ids, c.id] : value.client_ids.filter((id) => id !== c.id),
                  })
                }
              />
              {c.name}
            </label>
          ))}
        </div>
      )}
    </fieldset>
  );
}

function useDebounced<T>(value: T, ms = 300): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return debounced;
}

function AddPersonDialog({
  moduleKey,
  me,
  onClose,
  onDone,
}: {
  moduleKey: string;
  me: AccessMe;
  onClose: () => void;
  onDone: () => void;
}) {
  const api = useMemo(() => accessApi(moduleKey), [moduleKey]);
  const [q, setQ] = useState("");
  const query = useDebounced(q.trim());
  const people = useQuery({
    queryKey: ["access", moduleKey, "people", query],
    queryFn: () => api.people(query),
    enabled: query.length >= 2,
  });
  const [chosen, setChosen] = useState<AccessPerson | null>(null);
  if (chosen) {
    return (
      <GrantDialog
        moduleKey={moduleKey}
        me={me}
        person={{ name: chosen.full_name, userId: chosen.user_id, entraObjectId: chosen.entra_object_id }}
        onClose={onClose}
        onDone={onDone}
      />
    );
  }
  return (
    <Modal open onClose={onClose} title="Add person">
      <FormField label="Search employees" htmlFor="access-search" hint="Name or email, at least 2 characters">
        <Input id="access-search" value={q} onChange={(e) => setQ(e.target.value)} autoFocus />
      </FormField>
      <div className="mt-3 space-y-2" aria-live="polite">
        {people.isFetching && <p className="text-sm text-dt-text-secondary">Searching…</p>}
        {people.isError && <p role="alert" className="text-sm text-dt-danger">{explain(people.error, "Search failed.")}</p>}
        {people.data && !people.data.directory_available && (
          <p className="text-xs text-dt-warning">The directory could not be searched; only people already in DijiOne are shown.</p>
        )}
        {people.data?.people.length === 0 && <p className="text-sm text-dt-text-secondary">No eligible employees found.</p>}
        {people.data?.people.map((p) => (
          <div key={p.user_id ?? p.entra_object_id} className="flex items-center justify-between gap-3 rounded-xl border border-dt-border p-3">
            <div className="min-w-0">
              <div className="truncate font-medium text-dt-text-primary">{p.full_name}</div>
              <div className="truncate text-xs text-dt-text-secondary">
                {p.email}
                {p.job_title && ` · ${p.job_title}`}
                {p.source === "DIRECTORY" && " · new to DijiOne"}
                {p.has_access && ` · has ${p.role_name}`}
              </div>
              {!p.can_grant && p.reason && <div className="text-xs text-dt-text-secondary">{p.reason}</div>}
            </div>
            <Button size="sm" variant="secondary" disabled={!p.can_grant} onClick={() => setChosen(p)}>
              Select
            </Button>
          </div>
        ))}
      </div>
    </Modal>
  );
}

function GrantDialog({
  moduleKey,
  me,
  person,
  current,
  onClose,
  onDone,
}: {
  moduleKey: string;
  me: AccessMe;
  person: { name: string; userId: number | null; entraObjectId?: string | null };
  current?: AccessSource;
  onClose: () => void;
  onDone: () => void;
}) {
  const api = useMemo(() => accessApi(moduleKey), [moduleKey]);
  const [role, setRole] = useState(
    me.grantable_roles.some((r) => r.key === current?.role) ? current!.role : me.grantable_roles[0]?.key ?? ""
  );
  const [scope, setScope] = useState<AccessClientScopeIn>(() => ({
    all_clients: Boolean(current?.scope?.all_clients && me.client_authority?.all_clients),
    client_ids: current?.scope?.all_clients ? [] : current?.scope?.clients.map((c) => c.id) ?? [],
  }));
  const save = useMutation({
    mutationFn: () => {
      const body = { role, ...(me.supports_client_scope ? { client_scope: scope } : {}) };
      return person.userId != null ? api.grant(person.userId, body) : api.onboard(person.entraObjectId!, body);
    },
    onSuccess: () => {
      onDone();
      onClose();
    },
  });
  const scopeMissing = me.supports_client_scope && !scope.all_clients && scope.client_ids.length === 0;
  return (
    <Modal open onClose={onClose} title={`Access for ${person.name}`}>
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate();
        }}
      >
        <FormField label="Role" htmlFor="access-role">
          <Select id="access-role" value={role} onChange={(e) => setRole(e.target.value)}>
            {me.grantable_roles.map((r) => (
              <option key={r.key} value={r.key}>
                {r.name}
              </option>
            ))}
          </Select>
        </FormField>
        {me.supports_client_scope && me.client_authority && (
          <ClientScopePicker authority={me.client_authority} value={scope} onChange={setScope} />
        )}
        {save.isError && <p role="alert" className="text-sm text-dt-danger">{explain(save.error, "Could not save.")}</p>}
        <div className="flex justify-end gap-2">
          <Button type="button" variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" loading={save.isPending} disabled={!role || scopeMissing}>
            Save access
          </Button>
        </div>
      </form>
    </Modal>
  );
}

function RemoveDialog({
  moduleKey,
  user,
  onClose,
  onDone,
}: {
  moduleKey: string;
  user: AppUser;
  onClose: () => void;
  onDone: () => void;
}) {
  const api = useMemo(() => accessApi(moduleKey), [moduleKey]);
  const preview = useQuery({
    queryKey: ["access", moduleKey, "revoke-preview", user.user_id],
    queryFn: () => api.revokePreview(user.user_id),
  });
  const [reason, setReason] = useState("");
  const remove = useMutation({
    mutationFn: () => api.revoke(user.user_id, reason),
    onSuccess: () => {
      onDone();
      onClose();
    },
  });
  const p = preview.data;
  return (
    <Modal open onClose={onClose} title={`Remove ${user.full_name}'s access`}>
      {preview.isLoading && <LoadingState />}
      {preview.isError && <ErrorState message={explain(preview.error, "Could not check.")} onRetry={() => preview.refetch()} />}
      {p && (
        <div className="space-y-3 text-sm">
          {!p.allowed ? (
            <p role="alert" className="text-dt-danger">{p.reason}</p>
          ) : (
            <>
              {p.removes_direct && <p>Removes the role granted here: <strong>{p.removes_direct.role_name}</strong>.</p>}
              {p.suspends.length > 0 && (
                <p>
                  Suspends, in this application only, access from:{" "}
                  {p.suspends.map((s) => `${s.group_name} (${s.role_name})`).join(", ")}. Group memberships and other
                  applications are not changed.
                </p>
              )}
            </>
          )}
          {p.keeps.length > 0 && (
            <p className="text-dt-text-secondary">
              Keeps mandatory access: {p.keeps.map((s) => `${s.group_name ?? SOURCE_LABEL[s.type]} (${s.role_name})`).join(", ")}.
            </p>
          )}
          {p.allowed && (
            <FormField label="Reason (recorded in the audit log)" htmlFor="access-reason">
              <Textarea id="access-reason" value={reason} onChange={(e) => setReason(e.target.value)} rows={2} />
            </FormField>
          )}
          {remove.isError && <p role="alert" className="text-dt-danger">{explain(remove.error, "Could not remove.")}</p>}
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={onClose}>
              Cancel
            </Button>
            {p.allowed && (
              <Button variant="danger" loading={remove.isPending} onClick={() => remove.mutate()}>
                Remove access
              </Button>
            )}
          </div>
        </div>
      )}
    </Modal>
  );
}

// --- Administrators ----------------------------------------------------------------------------

function AdminsTab({ moduleKey }: { moduleKey: string }) {
  const api = useMemo(() => accessApi(moduleKey), [moduleKey]);
  const admins = useQuery({ queryKey: ["access", moduleKey, "admins"], queryFn: api.admins });
  if (admins.isLoading) return <LoadingState />;
  if (admins.isError) return <ErrorState message={explain(admins.error, "Administrators could not be loaded.")} onRetry={() => admins.refetch()} />;
  return (
    <Card>
      <CardContent className="p-0">
        <Table>
          <Thead>
            <Tr>
              <Th>Administrator</Th>
              <Th>May grant</Th>
              <Th>Clients</Th>
              <Th>Appointed by</Th>
            </Tr>
          </Thead>
          <tbody>
            {admins.data?.map((a) => (
              <Tr key={a.user_id}>
                <Td>
                  <div className="font-medium text-dt-text-primary">{a.full_name}</div>
                  <div className="text-xs text-dt-text-secondary">{a.email}</div>
                </Td>
                <Td>{a.grantable_roles.map((r) => r.name).join(", ")}</Td>
                <Td>{a.client_authority ? scopeText(a.client_authority) : "—"}</Td>
                <Td>{a.appointed_by_name ?? "—"}</Td>
              </Tr>
            ))}
          </tbody>
        </Table>
        <p className="px-4 py-3 text-xs text-dt-text-secondary">Administrators are appointed and removed by a Super Admin in Central Admin.</p>
      </CardContent>
    </Card>
  );
}
