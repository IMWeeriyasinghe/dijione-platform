"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Card, EmptyState, LoadingState, PageHeader, Table, Td, Th, Thead, Tr } from "@dijione/design-system";
import { DateRange, Page, QueryError, RequirePermission } from "@/components/ui";
import { management, type ClientAdoption } from "@/lib/api";
import { addDays, localDate } from "@/lib/format";
import { PERM } from "@/lib/atwork-scope";
import { useDisplay } from "@/lib/hooks";

function AdoptionBar({ pct }: { pct: number }) {
  return (
    <div className="flex items-center gap-2">
      <div className="h-2 w-32 overflow-hidden rounded-full bg-dt-surface-warm">
        <div className="h-full rounded-full bg-dt-burnt-orange" style={{ width: `${Math.min(100, pct)}%` }} />
      </div>
      <span className="text-xs text-dt-text-secondary">{pct.toFixed(0)}%</span>
    </div>
  );
}

function ClientRow({ row }: { row: ClientAdoption }) {
  const total = row.office_sessions + row.remote_sessions;
  const officePct = total > 0 ? Math.round((row.office_sessions / total) * 100) : 0;
  return (
    <Tr>
      <Td><span className="font-medium">{row.client}</span></Td>
      <Td>{row.adopted_employees}</Td>
      <Td><AdoptionBar pct={row.adoption_pct} /></Td>
      <Td>{row.office_sessions} <span className="text-xs text-dt-text-secondary">({officePct}%)</span></Td>
      <Td>{row.remote_sessions} <span className="text-xs text-dt-text-secondary">({100 - officePct}%)</span></Td>
      <Td>{row.net_hours.toFixed(1)}h</Td>
      {row.unverified_hours > 0 && <Td className="text-dt-warning">{row.unverified_hours.toFixed(1)}h</Td>}
      {row.unverified_hours === 0 && <Td className="text-dt-text-secondary">—</Td>}
    </Tr>
  );
}

function Screen() {
  const { zone } = useDisplay();
  const [range, setRange] = useState(() => {
    const to = localDate(Date.now(), zone);
    return { from: addDays(to, -29), to };
  });

  const query = useQuery({
    queryKey: ["atwork", "analytics", range.from, range.to],
    queryFn: () => management.analytics({ date_from: range.from, date_to: range.to }),
  });

  return (
    <>
      <PageHeader
        title="Client Analytics"
        description="Adoption, work mode distribution and confirmed hours by client for the selected period."
      />
      <Card className="mb-6 p-4">
        <DateRange from={range.from} to={range.to} onApply={(from, to) => setRange({ from, to })} />
      </Card>

      {query.isLoading ? (
        <LoadingState />
      ) : !query.data ? (
        <QueryError error={query.error} retry={() => query.refetch()} />
      ) : query.data.by_client.length === 0 ? (
        <EmptyState title="No data for the selected period" />
      ) : (
        <Table>
          <Thead>
            <Tr>
              <Th>Client</Th>
              <Th>Employees with sessions</Th>
              <Th>Adoption</Th>
              <Th>Office sessions</Th>
              <Th>Remote sessions</Th>
              <Th>Net hours</Th>
              <Th>Unverified hours</Th>
            </Tr>
          </Thead>
          <tbody>
            {query.data.by_client.map((row) => (
              <ClientRow key={row.client} row={row} />
            ))}
          </tbody>
        </Table>
      )}
    </>
  );
}

export default function AnalyticsPage() {
  return (
    <Page>
      <RequirePermission permission={[PERM.MANAGEMENT, PERM.READ_ALL, PERM.BP_ACCESS]} title="Attendance visibility required">
        <Screen />
      </RequirePermission>
    </Page>
  );
}
