"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, Card, EmptyState, FormField, Input, LoadingState, PageHeader, Table, Td, Th, Thead, Tr } from "@dijione/design-system";
import { Notice, Page, QueryError, RequirePermission } from "@/components/ui";
import { errorMessage, management, type BPGrant, type BPScopeEmployee } from "@/lib/api";
import { PERM } from "@/lib/atwork-scope";

// ─── Grant BP form ────────────────────────────────────────────────────────────

function GrantBPForm({ onDone }: { onDone: () => void }) {
  const [userId, setUserId] = useState("");
  const grant = useMutation({
    mutationFn: () => management.grantBP(Number(userId)),
    onSuccess: () => { setUserId(""); onDone(); },
  });
  return (
    <Card className="mb-6 max-w-sm space-y-3 p-4">
      <h3 className="text-sm font-semibold">Grant BP Access</h3>
      <p className="text-xs text-dt-text-secondary">
        Enter the platform user ID of the employee who will receive Business Partner access.
        They will be able to view Management for their assigned employees only.
      </p>
      {grant.isError && <Notice tone="error">{errorMessage(grant.error)}</Notice>}
      <FormField label="Platform User ID" htmlFor="bp-uid">
        <Input id="bp-uid" type="number" min={1} value={userId} onChange={(e) => setUserId(e.target.value)} placeholder="e.g. 42" />
      </FormField>
      <Button
        variant="primary"
        loading={grant.isPending}
        disabled={!userId || isNaN(Number(userId))}
        onClick={() => grant.mutate()}
      >
        Grant access
      </Button>
    </Card>
  );
}

// ─── Scope editor for a single BP ────────────────────────────────────────────

function BPScopePanel({ bp }: { bp: BPGrant }) {
  const qc = useQueryClient();
  const [addId, setAddId] = useState("");
  const scope = useQuery({
    queryKey: ["atwork", "bp-scope", bp.platform_user_id],
    queryFn: () => management.bpScope(bp.platform_user_id),
  });
  const add = useMutation({
    mutationFn: () => management.addBPScope(bp.platform_user_id, Number(addId)),
    onSuccess: () => { setAddId(""); void qc.invalidateQueries({ queryKey: ["atwork", "bp-scope", bp.platform_user_id] }); void qc.invalidateQueries({ queryKey: ["atwork", "bps"] }); },
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
          <p className="text-xs text-dt-text-secondary">No employees assigned — this BP sees an empty view.</p>
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
      <div className="flex items-end gap-2">
        <FormField label="Add employee (user ID)" htmlFor={`add-emp-${bp.platform_user_id}`}>
          <Input
            id={`add-emp-${bp.platform_user_id}`}
            type="number"
            min={1}
            placeholder="User ID"
            value={addId}
            onChange={(e) => setAddId(e.target.value)}
            className="w-28"
          />
        </FormField>
        <Button size="sm" variant="secondary" loading={add.isPending} disabled={!addId} onClick={() => add.mutate()}>
          Add
        </Button>
      </div>
      {add.isError && <div className="mt-2"><Notice tone="error">{errorMessage(add.error)}</Notice></div>}
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
        An employee not in a BP's scope is not visible to them. BPs cannot access another employee by
        changing a URL or parameter — authorization is enforced server-side.
      </div>

      <GrantBPForm onDone={() => void qc.invalidateQueries({ queryKey: ["atwork", "bps"] })} />

      {bps.isLoading ? <LoadingState /> : !bps.data ? <QueryError error={bps.error} retry={() => bps.refetch()} /> : bps.data.items.length === 0 ? (
        <EmptyState title="No BPs granted" description="Use the form above to grant BP access to an employee." />
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

export default function BPAccessPage() {
  return (
    <Page>
      <RequirePermission permission={PERM.ACCESS_MANAGE} title="Access administration required">
        <Screen />
      </RequirePermission>
    </Page>
  );
}
