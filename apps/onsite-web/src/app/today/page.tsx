"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { EmptyState, ErrorState, LoadingState, PageHeader, Table, Td, Th, Thead, Tr } from "@dijione/design-system";
import { CalendarDays } from "lucide-react";
import { ExportButton } from "@/components/ExportButton";
import { DateInput, DepartmentSelect, FilterRow, IdentitySelect, Pager, SelectFilter, SiteSelect, TextFilter } from "@/components/FilterBar";
import { EmployeeCell, FlagChips } from "@/components/FlagChips";
import { SiteProvider, useSite } from "@/components/SiteContext";
import { getToday, REVIEW_FLAGS } from "@/lib/dashboard";
import { FLAG_LABEL, formatSpan, localTime } from "@/lib/flags";

const SORTS = [
  { value: "first_activity", label: "First activity (earliest)" },
  { value: "-latest_activity", label: "Latest activity (latest)" },
  { value: "-punch_count", label: "Activity count (most)" },
  { value: "-span", label: "Activity span (longest)" },
  { value: "employee", label: "Employee (A–Z)" },
  { value: "-flags", label: "Review flags (most)" },
];

function TodayView() {
  const { site } = useSite();
  const [day, setDay] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const [empCode, setEmpCode] = useState("");
  const [department, setDepartment] = useState("");
  const [identity, setIdentity] = useState("");
  const [review, setReview] = useState("");
  const [sort, setSort] = useState("first_activity");
  const [page, setPage] = useState(1);
  const date = day ?? site.today;
  const filters = { site_id: site.site_id, date, q: q || undefined, emp_code: empCode.trim() || undefined, department: department || undefined,
    identity_class: identity || undefined, review: review || undefined };
  const params = { ...filters, sort, page, page_size: 50 };
  const query = useQuery({ queryKey: ["onsite-today", params], queryFn: () => getToday(params), refetchInterval: 60_000 });
  const reset = <T,>(set: (v: T) => void) => (v: T) => { set(v); setPage(1); };

  return (
    <div>
      <PageHeader title="Today" description="First activity, latest activity and activity count per employee, in site-local time."
        action={<ExportButton path="today" params={filters} />} />
      <FilterRow>
        <SiteSelect />
        <DateInput label="Date" value={date} onChange={reset(setDay)} />
        {site.last_activity_date && site.last_activity_date !== date && (
          <button type="button" className="text-sm font-medium text-dt-burnt-orange underline underline-offset-2" onClick={() => reset(setDay)(site.last_activity_date)}>
            Latest activity day
          </button>
        )}
      </FilterRow>
      <FilterRow>
        <TextFilter label="Search employee or code" value={q} onChange={reset(setQ)} />
        <TextFilter label="Employee Number" value={empCode} onChange={reset(setEmpCode)} />
        <DepartmentSelect value={department} onChange={reset(setDepartment)} />
        <IdentitySelect value={identity} onChange={reset(setIdentity)} />
        <SelectFilter label="Review status" value={review} onChange={reset(setReview)}
          options={[{ value: "", label: "All activity" }, { value: "needs_review", label: "Needs review" }, { value: "no_flags", label: "No review flags" },
            ...REVIEW_FLAGS.map((f) => ({ value: f, label: FLAG_LABEL[f] }))]} />
        <SelectFilter label="Sort" value={sort} onChange={reset(setSort)} options={SORTS} />
      </FilterRow>
      {query.isLoading ? <LoadingState label="Loading activity…" /> : query.isError || !query.data ? <ErrorState onRetry={() => query.refetch()} /> :
        query.data.total === 0 ? (
          <EmptyState icon={CalendarDays} title="No activity recorded" description={`No attendance activity is recorded for ${date} with the current filters.`} />
        ) : (
          <>
            <Table>
              <Thead><Tr><Th>Employee</Th><Th>Department</Th><Th>First activity</Th><Th>Latest activity</Th><Th>Count</Th><Th>Span</Th><Th>Terminals</Th><Th>Review</Th></Tr></Thead>
              <tbody>
                {query.data.items.map((r) => (
                  <Tr key={r.emp_code}>
                    <Td><EmployeeCell name={r.employee_name} code={r.emp_code} /></Td>
                    <Td>{r.department ?? "—"}</Td>
                    <Td>{localTime(r.first_activity_local)}</Td>
                    <Td>{localTime(r.latest_activity_local)}</Td>
                    <Td className="tabular-nums">{r.punch_count}</Td>
                    <Td>{formatSpan(r.span_minutes)}</Td>
                    <Td>{r.terminal_names.join(", ") || "—"}</Td>
                    <Td><FlagChips flags={r.flags} /></Td>
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

export default function TodayPage() {
  return <SiteProvider><TodayView /></SiteProvider>;
}
