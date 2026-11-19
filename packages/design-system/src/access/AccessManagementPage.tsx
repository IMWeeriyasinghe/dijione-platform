"use client";

import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ShieldCheck, UserPlus, Users } from "lucide-react";
import { ApiError, accessApi, useAuthorizedImage } from "@dijione/auth-client";
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

/** Profile photo (Microsoft Entra, proxied by Platform Core for access administrators) or
 * initials. The browser never calls Microsoft Graph and never sees a Graph token. */
export function PersonAvatar({ name, photoPath, size = 36 }: { name: string; photoPath?: string | null; size?: number }) {
  const url = useAuthorizedImage(photoPath ?? null);
  const words = name.trim().split(/\s+/).filter(Boolean);
  const initials = words.length ? (words[0][0] + (words.length > 1 ? words[words.length - 1][0] : "")).toUpperCase() : "?";
  return (
    <span
      className="relative grid shrink-0 place-items-center overflow-hidden rounded-full bg-dt-cream text-xs font-semibold text-dt-burnt-orange"
      style={{ width: size, height: size }}
      aria-hidden
    >
      {initials}
      {url && <img src={url} alt="" className="absolute inset-0 size-full object-cover" />}
    </span>
  );
}

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
                      <div className="flex items-center gap-3">
                        <PersonAvatar name={u.full_name} photoPath={u.has_photo ? api.userPhotoPath(u.user_id) : null} />
                        <div className="min-w-0">
                          <div className="font-medium text-dt-text-primary">{u.full_name}</div>
                          <div className="break-all text-xs text-dt-text-secondary">{u.email}</div>
                        </div>
                      </div>
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
          person={{ name: editing.full_name, userId: editing.user_id, email: editing.email,
            photoPath: editing.has_photo ? api.userPhotoPath(editing.user_id) : null }}
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
  const photoPath = (p: AccessPerson) =>
    !p.has_photo ? null : p.user_id != null ? api.userPhotoPath(p.user_id) : p.entra_object_id ? api.directoryPhotoPath(p.entra_object_id) : null;
  if (chosen) {
    return (
      <GrantDialog
        moduleKey={moduleKey}
        me={me}
        person={{ name: chosen.full_name, userId: chosen.user_id, entraObjectId: chosen.entra_object_id, email: chosen.email,
          upn: chosen.user_principal_name, title: chosen.job_title, photoPath: photoPath(chosen),
          note: chosen.source === "DIRECTORY" ? "New to DijiOne: the profile is created from Microsoft Entra ID when you grant access." : null }}
        onBack={() => setChosen(null)}
        onClose={onClose}
        onDone={onDone}
      />
    );
  }
  const results = people.data?.people ?? [];
  return (
    <Modal open onClose={onClose} title="Add person">
      <FormField label="Search Microsoft Entra ID" htmlFor="access-search"
        hint="Name, email address or user principal name, at least 2 characters">
        <Input id="access-search" type="search" value={q} onChange={(e) => setQ(e.target.value)} autoFocus autoComplete="off"
          aria-controls="access-results" />
      </FormField>
      <div className="mt-3 space-y-2" aria-live="polite" aria-busy={people.isFetching}>
        {people.isFetching && <p className="text-sm text-dt-text-secondary">Searching the directory…</p>}
        {people.isError && <p role="alert" className="text-sm text-dt-danger">{explain(people.error, "Search failed.")}</p>}
        {people.data && !people.data.directory_available && (
          <p className="text-xs text-dt-warning">Microsoft Entra ID could not be searched just now; only people already in DijiOne are shown.</p>
        )}
        {people.data && results.length === 0 && !people.isFetching && (
          <p className="text-sm text-dt-text-secondary">Nobody matches “{query}”.</p>
        )}
        {query.length < 2 && <p className="text-sm text-dt-text-secondary">Start typing to search the organisation directory.</p>}
      </div>
      {results.length > 0 && (
        <ul id="access-results" className="mt-2 max-h-[55vh] space-y-2 overflow-y-auto pr-1" aria-label="Directory search results">
          {results.map((p) => {
            const upn = p.user_principal_name && p.user_principal_name.toLowerCase() !== p.email.toLowerCase() ? p.user_principal_name : null;
            const status = p.has_access ? `Has ${p.role_name}` : p.can_grant ? (p.source === "DIRECTORY" ? "New to DijiOne" : "No access yet") : "Not eligible";
            return (
              <li key={p.user_id ?? p.entra_object_id}
                className="flex flex-wrap items-center gap-3 rounded-xl border border-dt-border p-3 sm:flex-nowrap">
                <PersonAvatar name={p.full_name} photoPath={photoPath(p)} />
                <div className="min-w-0 flex-1">
                  <div className="font-medium text-dt-text-primary">{p.full_name}</div>
                  <div className="break-all text-xs text-dt-text-secondary">{p.email}{upn && <> · {upn}</>}</div>
                  {p.job_title && <div className="text-xs text-dt-text-secondary">{p.job_title}{p.department ? ` · ${p.department}` : ""}</div>}
                  <div className="mt-1 flex flex-wrap items-center gap-2">
                    <span className={`rounded-full border px-2 py-0.5 text-xs ${p.has_access ? "border-dt-orange/40 bg-dt-orange/10 text-dt-burnt-orange" : p.can_grant ? "border-dt-border bg-dt-surface-warm text-dt-text-secondary" : "border-dt-border text-dt-text-secondary"}`}>
                      {status}
                    </span>
                    {!p.can_grant && p.reason && <span className="text-xs text-dt-text-secondary">{p.reason}</span>}
                  </div>
                </div>
                <Button size="sm" variant="secondary" disabled={!p.can_grant} onClick={() => setChosen(p)}
                  aria-label={`Select ${p.full_name}${p.can_grant ? "" : " (not available)"}`}>
                  Select
                </Button>
              </li>
            );
          })}
        </ul>
      )}
    </Modal>
  );
}

function GrantDialog({
  moduleKey,
  me,
  person,
  current,
  onBack,
  onClose,
  onDone,
}: {
  moduleKey: string;
  me: AccessMe;
  person: {
    name: string; userId: number | null; entraObjectId?: string | null; email?: string | null; upn?: string | null;
    title?: string | null; photoPath?: string | null; note?: string | null;
  };
  current?: AccessSource;
  onBack?: () => void;
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
    onSuccess: () => onDone(),
  });
  const scopeMissing = me.supports_client_scope && !scope.all_clients && scope.client_ids.length === 0;
  const upn = person.upn && person.upn.toLowerCase() !== (person.email ?? "").toLowerCase() ? person.upn : null;
  const identity = (
    <div className="flex items-center gap-3 rounded-xl border border-dt-border bg-dt-surface-warm p-3">
      <PersonAvatar name={person.name} photoPath={person.photoPath} size={44} />
      <div className="min-w-0 text-sm">
        <div className="font-medium text-dt-text-primary">{person.name}</div>
        {person.email && <div className="break-all text-xs text-dt-text-secondary">{person.email}{upn && <> · {upn}</>}</div>}
        {person.title && <div className="text-xs text-dt-text-secondary">{person.title}</div>}
      </div>
    </div>
  );
  if (save.data) {
    const r = save.data;
    return (
      <Modal open onClose={onClose} title="Access granted">
        <div className="space-y-4" role="status">
          {identity}
          <dl className="grid grid-cols-1 gap-2 text-sm sm:grid-cols-2">
            <div><dt className="text-xs text-dt-text-secondary">Access now</dt><dd className="font-medium">{r.has_access ? r.role_name : "No access"}</dd></div>
            <div><dt className="text-xs text-dt-text-secondary">From</dt><dd><Sources sources={r.sources} suspended={Boolean(r.suspension)} /></dd></div>
            {r.recorded_change && (
              <div className="sm:col-span-2">
                <dt className="text-xs text-dt-text-secondary">Audit record</dt>
                <dd>#{r.recorded_change.audit_id} · {r.recorded_change.action} by {r.recorded_change.actor_name ?? "you"} ·{" "}
                  {new Date(r.recorded_change.at).toLocaleString()}</dd>
              </div>
            )}
          </dl>
          <p className="text-xs text-dt-text-secondary">The change applies at the person's next sign-in or session refresh.</p>
          <div className="flex justify-end"><Button onClick={onClose}>Done</Button></div>
        </div>
      </Modal>
    );
  }
  return (
    <Modal open onClose={onClose} title={`Access for ${person.name}`}>
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate();
        }}
      >
        {identity}
        {person.note && <p className="text-xs text-dt-text-secondary">{person.note}</p>}
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
        <div className="flex flex-wrap justify-end gap-2">
          {onBack && (
            <Button type="button" variant="ghost" onClick={onBack}>
              Back to search
            </Button>
          )}
          <Button type="button" variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" loading={save.isPending} disabled={!role || scopeMissing}>
            {person.userId == null ? "Confirm and grant access" : "Save access"}
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
