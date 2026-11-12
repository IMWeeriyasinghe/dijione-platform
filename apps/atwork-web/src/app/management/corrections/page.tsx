"use client";

import Link from "next/link";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { EmptyState, FormField, LoadingState, PageHeader, Select, StatusBadge, Table, Td, Th, Thead, Tr } from "@dijione/design-system";
import { CORRECTION_TITLE, Page, Pager, QueryError, RequirePermission } from "@/components/ui";
import { management } from "@/lib/api";
import { dateTime } from "@/lib/format";
import { PERM } from "@/lib/atwork-scope";
import { useDisplay } from "@/lib/hooks";

const LIMIT = 25;

function Screen() {
  const { zone, format } = useDisplay();
  const [status, setStatus] = useState("PENDING");
  const [offset, setOffset] = useState(0);
  const query = useQuery({ queryKey: ["atwork", "queue", status, offset], queryFn: () => management.corrections({ status, limit: LIMIT, offset }), refetchOnWindowFocus: "always" });
  return (
    <>
      <PageHeader title="Corrections" description="Review employee correction requests." />
      <div className="mb-4 max-w-xs"><FormField label="Status" htmlFor="queue-status"><Select id="queue-status" value={status} onChange={(e) => { setStatus(e.target.value); setOffset(0); }}><option value="PENDING">Pending</option><option value="APPROVED">Approved</option><option value="REJECTED">Rejected</option><option value="WITHDRAWN">Withdrawn</option><option value="">All history</option></Select></FormField></div>
      {query.isLoading ? <LoadingState /> : !query.data ? <QueryError error={query.error} retry={() => query.refetch()} /> : query.data.items.length === 0 ? <EmptyState title="No requests here" /> : (
        <>
          <Table>
            <Thead><Tr><Th>Employee</Th><Th>Type</Th><Th>Requested</Th><Th>Status</Th></Tr></Thead>
            <tbody>{query.data.items.map((c) => <Tr key={c.id}><Td><Link className="font-medium underline-offset-2 hover:underline" href={`/management/corrections/${c.id}`}>{c.employee_name}</Link></Td><Td>{CORRECTION_TITLE[c.kind]}</Td><Td>{dateTime(c.created_at, zone, format)}</Td><Td><StatusBadge status={c.status} /></Td></Tr>)}</tbody>
          </Table>
          <Pager total={query.data.total} limit={LIMIT} offset={offset} onChange={setOffset} />
        </>
      )}
    </>
  );
}

export default function CorrectionsPage() {
  return <Page><RequirePermission permission={[PERM.MANAGEMENT, PERM.REVIEW]} title="Correction review access required"><Screen /></RequirePermission></Page>;
}
