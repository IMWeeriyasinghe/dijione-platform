"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Button, Card, CardContent, ErrorState, LoadingState, MetricCard, PageHeader } from "@dijione/design-system";
import { CircleAlert, CircleCheck, CircleHelp, CircleSlash, Clock } from "lucide-react";
import { AdminOnly } from "@/components/AdminOnly";
import { DataView, Facts } from "@/components/DataView";
import { IdentityBadge } from "@/components/FlagChips";
import { Person } from "@/components/kit";
import { fmtNum } from "@/lib/period";
import type { IdentityRow } from "@/lib/types";
import { PERM } from "@/lib/onsite-scope";
import { downloadIdentityCsv, getIdentityReport } from "@/lib/api";
import { IDENTITY_LABEL } from "@/lib/format";
import type { IdentityClass } from "@/lib/types";

const CLASSES: { key: IdentityClass; icon: typeof CircleCheck }[] = [
  { key: "MATCHED_ACTIVE", icon: CircleCheck },
  { key: "MATCHED_INACTIVE", icon: CircleSlash },
  { key: "MATCHED_BEFORE_HIRE", icon: Clock },
  { key: "AMBIGUOUS", icon: CircleHelp },
  { key: "UNMATCHED", icon: CircleAlert },
];

function IdentityView() {
  const [filter, setFilter] = useState<IdentityClass | "ALL">("ALL");
  const [exportError, setExportError] = useState(false);
  const report = useQuery({ queryKey: ["onsite-identity"], queryFn: getIdentityReport });

  if (report.isLoading) return <LoadingState label="Matching attendance codes…" />;
  if (report.isError || !report.data) return <ErrorState onRetry={() => report.refetch()} />;
  const { summary, rows, directory_available } = report.data;
  const visible = filter === "ALL" ? rows : rows.filter((r) => r.identity_class === filter);

  return (
    <div className="space-y-4">
      <PageHeader
        title="Identity Match"
        description="Attendance EmpCodes matched to BambooHR Employee Numbers by exact text equality. Nothing is auto-corrected."
        action={
          <Button
            variant="secondary"
            onClick={async () => {
              setExportError(false);
              try { await downloadIdentityCsv(); } catch { setExportError(true); }
            }}
          >
            Export CSV
          </Button>
        }
      />
      {exportError && <p className="text-sm text-dt-danger">Export failed. Please try again.</p>}

      {!directory_available ? (
        <Card>
          <CardContent className="py-4 text-sm text-dt-burnt-orange">
            Employee details unavailable — the Workforce Directory could not be reached. Showing attendance codes only.
          </CardContent>
        </Card>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-5">
            {CLASSES.map(({ key, icon }) => (
              <button key={key} type="button" className="text-left" onClick={() => setFilter(filter === key ? "ALL" : key)}>
                <MetricCard label={IDENTITY_LABEL[key]} value={summary[key] ?? 0} icon={icon} tone={filter === key ? "brand" : "neutral"} />
              </button>
            ))}
          </div>
          <p className="text-sm text-dt-text-secondary">
            Workforce Directory: {summary.directory_total ?? 0} employees ·{" "}
            {summary.directory_blank_employee_numbers ?? 0} with a blank Employee Number ·{" "}
            {summary.directory_duplicate_employee_numbers ?? 0} duplicated Employee Number(s) ·{" "}
            {summary.directory_entries_without_attendance ?? 0} without attendance at enabled sites
          </p>
        </>
      )}

      <DataView<IdentityRow> caption="Attendance codes and their directory match" rows={visible} rowKey={(r) => r.emp_code}
        columns={[
          { key: "code", header: "Employee Code", cell: (r) => <Person name={matchName(r)} code={r.emp_code} meta={r.matches[0]?.department ?? undefined} size="sm" /> },
          { key: "match", header: "Match", cell: (r) => <IdentityBadge cls={r.identity_class} /> },
          { key: "events", header: "Events", align: "right", cell: (r) => fmtNum(r.event_count) },
          { key: "first", header: "First seen", minWidth: "lg", cell: (r) => r.first_seen },
          { key: "last", header: "Last seen", cell: (r) => r.last_seen },
          { key: "matches", header: "Directory records", align: "right", cell: (r) => r.matches.length },
        ]}
        card={(r) => (
          <div className="space-y-2">
            <div className="flex items-start justify-between gap-2">
              <Person name={matchName(r)} code={r.emp_code} meta={r.matches[0]?.department ?? undefined} size="sm" />
              <IdentityBadge cls={r.identity_class} />
            </div>
            <Facts cols={3} items={[["Events", fmtNum(r.event_count)], ["First seen", r.first_seen], ["Last seen", r.last_seen]]} />
          </div>
        )} />
    </div>
  );
}

function matchName(r: IdentityRow): string | null {
  return r.matches.length === 1 ? r.matches[0].display_name : null;
}

export default function IdentityMatchPage() {
  return <AdminOnly permission={PERM.IDENTITY}><IdentityView /></AdminOnly>;
}
