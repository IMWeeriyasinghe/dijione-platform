"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Button, EmptyState, ErrorState, LoadingState, PageHeader, Table, Td, Th, Thead, Tr } from "@dijione/design-system";
import { Activity } from "lucide-react";
import { DateInput, FilterRow, Pager, SelectFilter, SiteSelect, TextFilter } from "@/components/FilterBar";
import { EmployeeCell, IdentityBadge } from "@/components/FlagChips";
import { SiteProvider, useSite } from "@/components/SiteContext";
import { downloadActivityCsv, getActivity, REVIEW_FLAGS } from "@/lib/dashboard";
import { addDays, FLAG_LABEL, localTime } from "@/lib/flags";
import { IDENTITY_LABEL } from "@/lib/format";
import { useOnsiteScope } from "@/lib/onsite-scope";
import type { IdentityClass } from "@/lib/types";

const IDENTITY: IdentityClass[] = ["MATCHED_ACTIVE", "MATCHED_INACTIVE", "MATCHED_BEFORE_HIRE", "AMBIGUOUS", "UNMATCHED"];

function ActivityView() {
  const { site } = useSite();
  const { scope } = useOnsiteScope();
  const end0 = site.last_activity_date ?? site.today;
  const [from, setFrom] = useState(addDays(end0, -6));
  const [to, setTo] = useState(end0);
  const [q, setQ] = useState("");
  const [terminal, setTerminal] = useState("");
  const [identity, setIdentity] = useState("");
  const [flag, setFlag] = useState("");
  const [page, setPage] = useState(1);
  const [exportError, setExportError] = useState(false);
  const filters = { site_id: site.site_id, date_from: from, date_to: to, q: q || undefined, terminal: terminal || undefined,
    identity_class: identity || undefined, flag: flag || undefined };
  const query = useQuery({ queryKey: ["onsite-activity", filters, page], queryFn: () => getActivity({ ...filters, page, page_size: 50 }) });
  const reset = <T,>(set: (v: T) => void) => (v: T) => { set(v); setPage(1); };
  const technical = Boolean(scope?.isAdmin);

  return (
    <div>
      <PageHeader
        title="Activity"
        description="Every recorded attendance activity, newest first. The raw device state is shown as recorded and is not interpreted."
        action={
          <Button variant="secondary" onClick={async () => {
            setExportError(false);
            try { await downloadActivityCsv(filters, `onsite-activity-${from}-${to}.csv`); } catch { setExportError(true); }
          }}>Export CSV</Button>
        }
      />
      {exportError && <p className="mb-2 text-sm text-dt-danger">Export failed. Please try again.</p>}
      <FilterRow>
        <SiteSelect />
        <DateInput label="From" value={from} onChange={reset(setFrom)} />
        <DateInput label="To" value={to} onChange={reset(setTo)} />
      </FilterRow>
      <FilterRow>
        <TextFilter label="Search employee or code" value={q} onChange={reset(setQ)} />
        <SelectFilter label="Terminal" value={terminal} onChange={reset(setTerminal)}
          options={[{ value: "", label: "All terminals" }, ...site.terminals.map((t) => ({ value: t, label: t }))]} />
        <SelectFilter label="Identity" value={identity} onChange={reset(setIdentity)}
          options={[{ value: "", label: "All identities" }, ...IDENTITY.map((c) => ({ value: c, label: IDENTITY_LABEL[c] }))]} />
        <SelectFilter label="Review flag" value={flag} onChange={reset(setFlag)}
          options={[{ value: "", label: "Any review status" }, ...REVIEW_FLAGS.map((f) => ({ value: f, label: FLAG_LABEL[f] }))]} />
      </FilterRow>
      {query.isLoading ? <LoadingState label="Loading activity…" /> : query.isError || !query.data ? <ErrorState onRetry={() => query.refetch()} /> :
        query.data.total === 0 ? <EmptyState icon={Activity} title="No activity recorded" description="No attendance activity matches the current filters." /> : (
          <>
            <Table>
              <Thead><Tr><Th>Local date &amp; time</Th><Th>Employee</Th><Th>Department</Th><Th>Terminal</Th><Th>Identity</Th><Th>Raw state</Th>{technical && <Th>Epoch</Th>}</Tr></Thead>
              <tbody>
                {query.data.items.map((e, i) => (
                  <Tr key={e.event_id ?? `${e.emp_code}-${e.local_time}-${i}`}>
                    <Td className="whitespace-nowrap">{e.local_date} {localTime(e.local_time)}</Td>
                    <Td><EmployeeCell name={e.employee_name} code={e.emp_code} /></Td>
                    <Td>{e.department ?? "—"}</Td>
                    <Td>{e.terminal ?? "—"}</Td>
                    <Td><IdentityBadge cls={e.identity_class} /></Td>
                    <Td className="font-mono text-xs">{e.punch_state_raw ?? "—"}</Td>
                    {technical && <Td className="tabular-nums">{e.source_epoch}</Td>}
                  </Tr>
                ))}
              </tbody>
            </Table>
            <Pager page={page} pageSize={50} total={query.data.total} onPage={setPage} />
          </>
        )}
    </div>
  );
}

export default function ActivityPage() {
  return <SiteProvider><ActivityView /></SiteProvider>;
}
