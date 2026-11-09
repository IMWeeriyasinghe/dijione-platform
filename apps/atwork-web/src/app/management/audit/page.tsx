"use client";

import { Suspense, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { EmptyState, FormField, LoadingState, PageHeader, Select, Table, Td, Th, Thead, Tr } from "@dijione/design-system";
import { useSearchParams } from "next/navigation";
import { Page, Pager, QueryError, RequirePermission } from "@/components/ui";
import { management } from "@/lib/api";
import { dateTime } from "@/lib/format";
import { PERM } from "@/lib/atwork-scope";
import { useDisplay } from "@/lib/hooks";

const LIMIT = 50;
const ACTIONS = ["CHECK_IN", "BREAK_START", "BREAK_END", "CHECK_OUT", "CORRECTION_REQUESTED", "CORRECTION_WITHDRAWN", "CORRECTION_APPROVED", "CORRECTION_REJECTED", "SESSION_CORRECTED", "SESSION_CREATED_BY_CORRECTION", "REPORT_EXPORTED", "SETTINGS_UPDATED"];
const pretty = (a: string) => a.charAt(0) + a.slice(1).toLowerCase().replaceAll("_", " ");

function Screen() {
  const { zone, format } = useDisplay();
  const session = useSearchParams().get("session") ?? undefined;
  const [action, setAction] = useState("");
  const [offset, setOffset] = useState(0);
  const query = useQuery({ queryKey: ["atwork", "audit", action, session, offset], queryFn: () => management.audit({ action, session_id: session, limit: LIMIT, offset }) });
  return (
    <>
      <PageHeader title="Audit History" description={session ? "Events for one attendance session." : "Every attendance change and Management action."} />
      <div className="mb-4 max-w-xs"><FormField label="Action" htmlFor="audit-action"><Select id="audit-action" value={action} onChange={(e) => { setAction(e.target.value); setOffset(0); }}><option value="">All actions</option>{ACTIONS.map((a) => <option key={a} value={a}>{pretty(a)}</option>)}</Select></FormField></div>
      {query.isLoading ? <LoadingState /> : !query.data ? <QueryError error={query.error} retry={() => query.refetch()} /> : query.data.items.length === 0 ? <EmptyState title="No audit events found" /> : (
        <>
          <Table><Thead><Tr><Th>When</Th><Th>Action</Th><Th>By</Th><Th>Employee</Th><Th>Change</Th></Tr></Thead><tbody>{query.data.items.map((e) => <Tr key={e.id}><Td className="whitespace-nowrap">{dateTime(e.occurred_at, zone, format)}</Td><Td>{pretty(e.action)}</Td><Td>{e.actor_name}</Td><Td>{e.subject_name}</Td><Td><details><summary className="cursor-pointer text-dt-burnt-orange">View</summary><pre className="mt-2 max-w-md overflow-x-auto text-xs">{JSON.stringify({ before: e.before_state, after: e.after_state }, null, 2)}</pre></details></Td></Tr>)}</tbody></Table>
          <Pager total={query.data.total} limit={LIMIT} offset={offset} onChange={setOffset} />
        </>
      )}
    </>
  );
}

export default function AuditPage() {
  return <Page><RequirePermission permission={[PERM.MANAGEMENT, PERM.AUDIT]} title="Audit access required"><Suspense fallback={<LoadingState />}><Screen /></Suspense></RequirePermission></Page>;
}
