"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, EmptyState, ErrorState, LoadingState, PageHeader } from "@dijione/design-system";
import { CheckCircle2 } from "lucide-react";
import { ExportButton } from "@/components/ExportButton";
import { DateInput, DepartmentSelect, FilterRow, IdentitySelect, Pager, SiteSelect, TextFilter } from "@/components/FilterBar";
import { EmployeeCell, FlagChips } from "@/components/FlagChips";
import { SiteProvider, useSite } from "@/components/SiteContext";
import { getExceptions, REVIEW_FLAGS, type ReviewFlag } from "@/lib/dashboard";
import { addDays, FLAG_LABEL, formatSpan, localTime } from "@/lib/flags";

function ExceptionsView() {
  const { site } = useSite();
  const end0 = site.last_activity_date ?? site.today;
  const [from, setFrom] = useState(addDays(end0, -6));
  const [to, setTo] = useState(end0);
  const [flag, setFlag] = useState<ReviewFlag | "">("");
  const [q, setQ] = useState("");
  const [empCode, setEmpCode] = useState("");
  const [department, setDepartment] = useState("");
  const [identity, setIdentity] = useState("");
  const [page, setPage] = useState(1);
  const filters = { site_id: site.site_id, date_from: from, date_to: to, flag: flag || undefined, q: q || undefined,
    emp_code: empCode.trim() || undefined, department: department || undefined, identity_class: identity || undefined };
  const params = { ...filters, page, page_size: 25 };
  const query = useQuery({ queryKey: ["onsite-exceptions", params], queryFn: () => getExceptions(params) });
  const reset = <T,>(set: (v: T) => void) => (v: T) => { set(v); setPage(1); };

  return (
    <div>
      <PageHeader title="Exceptions" description="Activity that may need a closer look. Flags are prompts for review only — nothing is changed automatically."
        action={<ExportButton path="exceptions" params={filters} />} />
      <FilterRow>
        <SiteSelect />
        <DateInput label="From" value={from} onChange={reset(setFrom)} />
        <DateInput label="To" value={to} onChange={reset(setTo)} />
      </FilterRow>
      <FilterRow>
        <TextFilter label="Search employee or code" value={q} onChange={reset(setQ)} />
        <TextFilter label="Employee Number" value={empCode} onChange={reset(setEmpCode)} />
        <DepartmentSelect value={department} onChange={reset(setDepartment)} />
        <IdentitySelect value={identity} onChange={reset(setIdentity)} />
      </FilterRow>
      {query.data && (
        <div className="mb-4 flex flex-wrap gap-2" role="group" aria-label="Filter by review flag">
          <button type="button" aria-pressed={flag === ""} onClick={() => reset(setFlag)("")}
            className={`rounded-full border px-3 py-1 text-sm ${flag === "" ? "border-dt-orange bg-dt-cream text-dt-burnt-orange" : "border-dt-border text-dt-text-secondary"}`}>
            All ({Object.values(query.data.counts).reduce((a, b) => a + b, 0)})
          </button>
          {REVIEW_FLAGS.map((f) => (
            <button key={f} type="button" aria-pressed={flag === f} onClick={() => reset(setFlag)(f)}
              className={`rounded-full border px-3 py-1 text-sm ${flag === f ? "border-dt-orange bg-dt-cream text-dt-burnt-orange" : "border-dt-border text-dt-text-secondary"}`}>
              {FLAG_LABEL[f]} ({query.data.counts[f] ?? 0})
            </button>
          ))}
        </div>
      )}
      {query.isLoading ? <LoadingState label="Loading review queue…" /> : query.isError || !query.data ? <ErrorState onRetry={() => query.refetch()} /> :
        query.data.total === 0 ? <EmptyState icon={CheckCircle2} title="Nothing needs review" description="No activity in this range matches the selected review flags." /> : (
          <>
            <ul className="space-y-3">
              {query.data.items.map((item) => (
                <li key={`${item.local_date}-${item.emp_code}`}>
                  <Card>
                    <CardContent className="grid gap-3 py-4 md:grid-cols-[minmax(12rem,1fr)_2fr]">
                      <div>
                        <EmployeeCell name={item.employee_name} code={item.emp_code} />
                        <p className="mt-1 text-sm text-dt-text-secondary">{item.local_date}{item.department ? ` · ${item.department}` : ""}</p>
                      </div>
                      <div className="space-y-2 text-sm">
                        <FlagChips flags={item.flags} />
                        <p className="text-dt-text-secondary">
                          First activity {localTime(item.first_activity_local)} · Latest activity {localTime(item.latest_activity_local)} ·{" "}
                          {item.punch_count} {item.punch_count === 1 ? "activity" : "activities"} · Span {formatSpan(item.span_minutes)}
                          {item.terminal_names.length ? ` · ${item.terminal_names.join(", ")}` : ""}
                        </p>
                        <ul className="list-disc pl-5 text-dt-text-secondary">
                          {item.reasons.map((r) => <li key={r.flag}>{r.reason}</li>)}
                        </ul>
                      </div>
                    </CardContent>
                  </Card>
                </li>
              ))}
            </ul>
            <Pager page={page} pageSize={25} total={query.data.total} onPage={setPage} />
          </>
        )}
    </div>
  );
}

export default function ExceptionsPage() {
  return <SiteProvider><ExceptionsView /></SiteProvider>;
}
