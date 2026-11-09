"use client";

import { use, useMemo, useState } from "react";
import { useInfiniteQuery } from "@tanstack/react-query";
import { Card, EmptyState, LoadingState, PageHeader } from "@dijione/design-system";
import { DateRange, Page, QueryError, RequirePermission, SessionRow, DayHeading } from "@/components/ui";
import { groupByDay } from "@/components/history";
import { Button } from "@dijione/design-system";
import { management } from "@/lib/api";
import { addDays, localDate } from "@/lib/format";
import { PERM } from "@/lib/atwork-scope";
import { useDisplay } from "@/lib/hooks";

function Screen({ id }: { id: string }) {
  const { zone, format } = useDisplay();
  const [range, setRange] = useState(() => {
    const to = localDate(Date.now(), zone);
    return { from: addDays(to, -29), to };
  });
  const query = useInfiniteQuery({
    queryKey: ["atwork", "employee", id, range],
    queryFn: ({ pageParam }) => management.employeeHistory(id, { date_from: range.from, date_to: range.to, limit: 20, offset: pageParam }),
    initialPageParam: 0,
    retry: false,
    getNextPageParam: (l) => (l.offset + l.limit < l.total ? l.offset + l.limit : undefined),
  });
  const pages = query.data?.pages;
  const sessions = useMemo(() => pages?.flatMap((p) => p.sessions) ?? [], [pages]);
  if (query.isLoading) return <LoadingState />;
  const first = pages?.[0];
  if (!first) return <QueryError error={query.error} retry={() => query.refetch()} />;
  return (
    <>
      <PageHeader title={first.employee.employee_name} description={first.employee.email ?? undefined} />
      <Card className="mb-6 p-4"><DateRange from={range.from} to={range.to} onApply={(from, to) => setRange({ from, to })} /></Card>
      {sessions.length === 0 ? <EmptyState title="No attendance in this range" /> : (
        <div className="space-y-6">
          {groupByDay(sessions, first.daily_totals, first.time_zone, new Date().toISOString()).map((g) => (
            <section key={g.day.date}>
              <DayHeading day={g.day.date} totals={g.day} />
              <div className="space-y-2">{g.sessions.map((s) => <SessionRow key={s.id} session={s} zone={first.time_zone} format={format} href={`/management/sessions/${s.id}`} />)}</div>
            </section>
          ))}
          {query.hasNextPage && <div className="text-center"><Button variant="secondary" loading={query.isFetchingNextPage} onClick={() => query.fetchNextPage()}>Load more</Button></div>}
        </div>
      )}
    </>
  );
}

export default function EmployeePage({ params }: { params: Promise<{ userId: string }> }) {
  const { userId } = use(params);
  return <Page><RequirePermission permission={[PERM.MANAGEMENT, PERM.READ_ALL]} title="Attendance visibility required"><Screen id={userId} /></RequirePermission></Page>;
}
