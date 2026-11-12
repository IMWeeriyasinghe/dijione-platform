"use client";

import Link from "next/link";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Button, EmptyState, FormField, Input, LoadingState, PageHeader, StatusBadge, Table, Td, Th, Thead, Tr } from "@dijione/design-system";
import { Page, Pager, QueryError, RequirePermission } from "@/components/ui";
import { management } from "@/lib/api";
import { PERM } from "@/lib/atwork-scope";

const LIMIT = 25;
const LABEL = { NOT_CHECKED_IN: "Not checked in", WORKING: "Working", ON_BREAK: "On break" };
const TONE = { NOT_CHECKED_IN: "NOT_STARTED", WORKING: "ACTIVE", ON_BREAK: "ON_HOLD" };

function Screen() {
  const [draft, setDraft] = useState("");
  const [q, setQ] = useState("");
  const [offset, setOffset] = useState(0);
  const query = useQuery({ queryKey: ["atwork", "employees", q, offset], queryFn: () => management.employees({ q, limit: LIMIT, offset }) });
  return (
    <>
      <PageHeader title="Employees" description="People who have recorded attendance in DijiAtWork." />
      <form className="mb-4 flex flex-wrap items-end gap-3" onSubmit={(e) => { e.preventDefault(); setQ(draft); setOffset(0); }}>
        <div className="min-w-64 flex-1"><FormField label="Search by name or email" htmlFor="q"><Input id="q" value={draft} onChange={(e) => setDraft(e.target.value)} /></FormField></div>
        <Button type="submit" variant="secondary">Search</Button>
      </form>
      {query.isLoading ? <LoadingState /> : !query.data ? <QueryError error={query.error} retry={() => query.refetch()} /> : query.data.items.length === 0 ? <EmptyState title="No employees found" /> : (
        <>
          <Table>
            <Thead><Tr><Th>Employee</Th><Th>Email</Th><Th>Status</Th></Tr></Thead>
            <tbody>{query.data.items.map((e) => <Tr key={e.platform_user_id}><Td><Link className="font-medium underline-offset-2 hover:underline" href={`/management/employees/${e.platform_user_id}`}>{e.employee_name}</Link></Td><Td>{e.email}</Td><Td><StatusBadge status={TONE[e.state]} label={LABEL[e.state]} /></Td></Tr>)}</tbody>
          </Table>
          <Pager total={query.data.total} limit={LIMIT} offset={offset} onChange={setOffset} />
        </>
      )}
    </>
  );
}

export default function EmployeesPage() {
  return <Page><RequirePermission permission={[PERM.MANAGEMENT, PERM.READ_ALL]} title="Attendance visibility required"><Screen /></RequirePermission></Page>;
}
