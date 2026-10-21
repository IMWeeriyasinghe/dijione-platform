"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Button, Card, CardContent, ErrorState, LoadingState, MetricCard, PageHeader, Table, Td, Th, Thead, Tr } from "@dijione/design-system";
import { CircleAlert, CircleCheck, CircleHelp, CircleSlash, Clock } from "lucide-react";
import { AdminOnly } from "@/components/AdminOnly";
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
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-5">
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

      <Table>
        <Thead>
          <Tr><Th>EmpCode</Th><Th>Match</Th><Th>Events</Th><Th>First seen</Th><Th>Last seen</Th><Th>Matches</Th></Tr>
        </Thead>
        <tbody>
          {visible.map((r) => (
            <Tr key={r.emp_code}>
              <Td className="font-mono">{r.emp_code}</Td>
              <Td>{r.identity_class ? IDENTITY_LABEL[r.identity_class] : "Employee details unavailable"}</Td>
              <Td>{r.event_count.toLocaleString()}</Td>
              <Td>{r.first_seen}</Td>
              <Td>{r.last_seen}</Td>
              <Td>{r.matches.length}</Td>
            </Tr>
          ))}
        </tbody>
      </Table>
    </div>
  );
}

export default function IdentityMatchPage() {
  return <AdminOnly><IdentityView /></AdminOnly>;
}
