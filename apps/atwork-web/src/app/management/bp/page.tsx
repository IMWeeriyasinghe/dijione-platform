"use client";

import { useCallback, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, Card, EmptyState, Input, LoadingState, PageHeader, Table, Td, Th, Thead, Tr } from "@dijione/design-system";
import { Notice, Page, QueryError, RequirePermission } from "@/components/ui";
import { errorMessage, management, type BPGrant, type BPScopeEmployee, type WorkforceSearchResult } from "@/lib/api";
import { PERM } from "@/lib/atwork-scope";

// ─── Employee directory search ────────────────────────────────────────────────

function EmployeeSearch({ onSelect }: { onSelect: (result: WorkforceSearchResult) => void }) {
  const [q, setQ] = useState("");
  const [triggered, setTriggered] = useState(false);

  const search = useQuery({
    queryKey: ["atwork", "bp-search", q],
    queryFn: () => management.bpEmployeeSearch(q),
    enabled: triggered && q.trim().length >= 2,
    staleTime: 30_000,
  });

  const handleSearch = useCallback(() => {
    if (q.trim().length >= 2) setTriggered(true);
  }, [q]);

  return (
    <div className="space-y-2">
      <div className="flex gap-2">
        <Input
          value={q}
          onChange={(e) => { setQ(e.target.value); setTriggered(false); }}
          onKeyDown={(e) => e.key === "Enter" && handleSearch()}
          placeholder="Search by name or email…"
          className="flex-1"
        />
        <Button variant="secondary" onClick={handleSearch} disabled={q.trim().length < 2}>
          Search
        </Button>
      </div>
      {triggered && search.isLoading && <p className="text-xs text-dt-text-secondary">Searching…</p>}
      {triggered && search.isError && <Notice tone="error">{errorMessage(search.error)}</Notice>}
      {triggered && search.data && (
        search.data.length === 0 ? (
          <p className="text-xs text-dt-text-secondary">No active employees found.</p>
        ) : (
          <ul className="divide-y divide-dt-border rounded-md border border-dt-border bg-dt-surface">
            {search.data.map((r) => (
              <li key={r.work_email} className="flex items-center justify-between gap-3 px-3 py-2 text-sm">
                <span>
                  <span className="font-medium">{r.display_name}</span>
                  <span className="ml-2 text-xs text-dt-text-secondary">{r.work_email}</span>
                  {r.department && <span className="ml-2 text-xs text-dt-text-secondary">· {r.department}</span>}
                  {r.platform_user_id === null && (
                    <span className="ml-2 text-xs text-dt-warning">· Not yet registered in DijiAtWork</span>
                  )}
                </span>
                <Button
                  size="sm"
                  variant="secondary"
                  disabled={r.platform_user_id === null}
                  onClick={() => { onSelect(r); setQ(""); setTriggered(false); }}
                >
                  Select
                </Button>
              </li>
            ))}
          </ul>
        )
      )}
    </div>
  );
}

// ─── Grant BP form ────────────────────────────────────────────────────────────

function GrantBPForm({ onDone }: { onDone: () => void }) {
  const [selected, setSelected] = useState<WorkforceSearchResult | null>(null);
  const grant = useMutation({
    mutationFn: () => management.grantBP(selected!.platform_user_id!),
    onSuccess: () => { setSelected(null); onDone(); },
  });

  return (
    <Card className="mb-6 max-w-lg space-y-3 p-4">
      <h3 className="text-sm font-semibold">Grant BP Access</h3>
      <p className="text-xs text-dt-text-secondary">
        Search the employee directory to find the person who should receive Business Partner access.
        They will be able to view Management for their assigned employees only.
      </p>
      {grant.isError && <Notice tone="error">{errorMessage(grant.error)}</Notice>}
      {selected ? (
        <div className="flex items-center justify-between gap-2 rounded border border-dt-border bg-dt-surface p-2 text-sm">
          <span>
            <span className="font-medium">{selected.display_name}</span>
            <span className="ml-2 text-xs text-dt-text-secondary">{selected.work_email}</span>
          </span>
          <div className="flex gap-2">
            <Button variant="primary" size="sm" loading={grant.isPending} onClick={() => grant.mutate()}>
              Confirm grant
            </Button>
            <Button variant="ghost" size="sm" onClick={() => setSelected(null)}>
              Clear
            </Button>
          </div>
        </div>
      ) : (
        <EmployeeSearch onSelect={setSelected} />
      )}
    </Card>
  );
}

// ─── Scope editor for a single BP ────────────────────────────────────────────

function BPScopePanel({ bp }: { bp: BPGrant }) {
  const qc = useQueryClient();
  const [adding, setAdding] = useState(false);
  const scope = useQuery({
    queryKey: ["atwork", "bp-scope", bp.platform_user_id],
    queryFn: () => management.bpScope(bp.platform_user_id),
  });
  const add = useMutation({
    mutationFn: (uid: number) => management.addBPScope(bp.platform_user_id, uid),
    onSuccess: () => { setAdding(false); void qc.invalidateQueries({ queryKey: ["atwork", "bp-scope", bp.platform_user_id] }); void qc.invalidateQueries({ queryKey: ["atwork", "bps"] }); },
  });
  const remove = useMutation({
    mutationFn: (eid: number) => management.removeBPScope(bp.platform_user_id, eid),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ["atwork", "bp-scope", bp.platform_user_id] }); void qc.invalidateQueries({ queryKey: ["atwork", "bps"] }); },
  });

  return (
    <div className="border-t border-dt-border pt-3">
      <h4 className="mb-2 text-xs font-semibold text-dt-text-secondary">Assigned employees</h4>
      {scope.isLoading ? <LoadingState /> : !scope.data ? <QueryError error={scope.error} retry={() => scope.refetch()} /> : (
        scope.data.length === 0 ? (
          <p className="mb-3 text-xs text-dt-text-secondary">No employees assigned — this BP sees an empty view.</p>
        ) : (
          <ul className="mb-3 space-y-1">
            {scope.data.map((emp: BPScopeEmployee) => (
              <li key={emp.platform_user_id} className="flex items-center justify-between gap-2 text-sm">
                <span>
                  {emp.employee_name}
                  {emp.client && <span className="ml-1 text-xs text-dt-text-secondary">· {emp.client}</span>}
                </span>
                <Button
                  size="sm"
                  variant="ghost"
                  loading={remove.isPending && remove.variables === emp.platform_user_id}
                  onClick={() => remove.mutate(emp.platform_user_id)}
                >
                  Remove
                </Button>
              </li>
            ))}
          </ul>
        )
      )}
      {add.isError && <div className="mb-2"><Notice tone="error">{errorMessage(add.error)}</Notice></div>}
      {adding ? (
        <div className="rounded border border-dt-border bg-dt-surface p-2">
          <p className="mb-2 text-xs font-medium">Add employee to scope</p>
          <EmployeeSearch
            onSelect={(r) => {
              if (r.platform_user_id !== null) add.mutate(r.platform_user_id);
            }}
          />
        </div>
      ) : (
        <Button size="sm" variant="secondary" onClick={() => setAdding(true)}>
          Add employee
        </Button>
      )}
    </div>
  );
}

// ─── BP row in the table ──────────────────────────────────────────────────────

function BPRow({ bp, onRevoke }: { bp: BPGrant; onRevoke: (id: number) => void }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <>
      <Tr>
        <Td><span className="font-medium">{bp.full_name}</span><br /><span className="text-xs text-dt-text-secondary">{bp.work_email ?? "—"}</span></Td>
        <Td>{bp.employee_count} employee{bp.employee_count !== 1 ? "s" : ""}</Td>
        <Td>
          <div className="flex flex-wrap gap-2">
            <Button size="sm" variant="secondary" onClick={() => setExpanded((x) => !x)}>
              {expanded ? "Hide scope" : "Manage scope"}
            </Button>
            <Button size="sm" variant="ghost" onClick={() => onRevoke(bp.platform_user_id)}>
              Revoke
            </Button>
          </div>
        </Td>
      </Tr>
      {expanded && (
        <Tr>
          <Td colSpan={3} className="bg-dt-surface-warm">
            <BPScopePanel bp={bp} />
          </Td>
        </Tr>
      )}
    </>
  );
}

// ─── Main screen ──────────────────────────────────────────────────────────────

function Screen() {
  const qc = useQueryClient();
  const bps = useQuery({ queryKey: ["atwork", "bps"], queryFn: management.bps });
  const revoke = useMutation({
    mutationFn: (id: number) => management.revokeBP(id),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["atwork", "bps"] }),
  });

  return (
    <>
      <PageHeader
        title="BP Access Management"
        description="Grant Business Partner access to employees and configure their management scope."
      />
      <div className="mb-4 rounded-lg border border-dt-warning bg-dt-warning/5 p-3 text-sm text-dt-text-primary">
        <strong>Security reminder:</strong> A BP can only see employees explicitly assigned to their scope.
        An employee not in a BP&apos;s scope is not visible to them. BPs cannot access another employee by
        changing a URL or parameter — authorization is enforced server-side.
      </div>

      <GrantBPForm onDone={() => void qc.invalidateQueries({ queryKey: ["atwork", "bps"] })} />

      {bps.isLoading ? <LoadingState /> : !bps.data ? <QueryError error={bps.error} retry={() => bps.refetch()} /> : bps.data.items.length === 0 ? (
        <EmptyState title="No BPs granted" description="Use the search above to find an employee and grant BP access." />
      ) : (
        <>
          {revoke.isError && <div className="mb-4"><Notice tone="error">{errorMessage(revoke.error)}</Notice></div>}
          <Table>
            <Thead>
              <Tr>
                <Th>Employee</Th>
                <Th>Scope</Th>
                <Th>Actions</Th>
              </Tr>
            </Thead>
            <tbody>
              {bps.data.items.map((bp) => (
                <BPRow key={bp.platform_user_id} bp={bp} onRevoke={(id) => revoke.mutate(id)} />
              ))}
            </tbody>
          </Table>
        </>
      )}
    </>
  );
}

/** Embeddable content — no Page or RequirePermission wrapper. */
export function BPAccessContent() {
  return <Screen />;
}

export default function BPAccessPage() {
  return (
    <Page>
      <RequirePermission permission={PERM.ACCESS_MANAGE} title="Access administration required">
        <Screen />
      </RequirePermission>
    </Page>
  );
}
