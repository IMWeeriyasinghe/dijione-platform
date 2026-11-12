"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { useInfiniteQuery } from "@tanstack/react-query";
import { Button, Card, EmptyState, LoadingState, PageHeader } from "@dijione/design-system";
import { HistoryList } from "@/components/history";
import { DateRange, OfflineBanner, Page, QueryError, RequirePermission } from "@/components/ui";
import { attendance } from "@/lib/api";
import { addDays, localDate } from "@/lib/format";
import { hasPermission, PERM, useAtworkScope } from "@/lib/atwork-scope";
import { useDisplay, usePolicy } from "@/lib/hooks";

const SIZE = 20;

function History({ initial }: { initial: { from: string; to: string } }) {
  const { scope } = useAtworkScope();
  const { format } = useDisplay();
  const [range, setRange] = useState(initial);
  const query = useInfiniteQuery({
    queryKey: ["atwork", "history", range],
    queryFn: ({ pageParam }) => attendance.history({ date_from: range.from, date_to: range.to, limit: SIZE, offset: pageParam }),
    initialPageParam: 0,
    getNextPageParam: (last) => (last.offset + last.limit < last.total ? last.offset + last.limit : undefined),
  });
  const pages = query.data?.pages;
  const sessions = useMemo(() => pages?.flatMap((p) => p.sessions) ?? [], [pages]);
  const first = pages?.[0];
  return (
    <>
      <PageHeader title="My Attendance" description="Your recorded sessions. Days without records are simply not shown." action={hasPermission(scope, PERM.REQUEST_OWN) ? <Link href="/requests/new"><Button variant="secondary">Request missing session</Button></Link> : undefined} />
      <OfflineBanner />
      <Card className="mb-6 p-4"><DateRange from={range.from} to={range.to} onApply={(from, to) => setRange({ from, to })} /></Card>
      {query.isLoading ? <LoadingState label="Loading attendance…" /> : !first ? <QueryError error={query.error} retry={() => query.refetch()} /> : sessions.length === 0 ? (
        <EmptyState title="No attendance in this range" description="Try a different date range." />
      ) : (
        <HistoryList sessions={sessions} daily={first.daily_totals} zone={first.time_zone} format={format} hrefFor={(s) => `/attendance/${s.id}`} total={first.total} onMore={() => query.fetchNextPage()} loading={query.isFetchingNextPage} />
      )}
    </>
  );
}

function Screen() {
  const policy = usePolicy();
  if (policy.isLoading) return <LoadingState />;
  if (!policy.data) return <QueryError error={policy.error} retry={() => policy.refetch()} />;
  const to = localDate(policy.data.server_time, policy.data.business_time_zone);
  return <History initial={{ from: addDays(to, -(policy.data.default_history_days - 1)), to }} />;
}

export default function AttendancePage() {
  return <Page><RequirePermission permission={PERM.READ_OWN} title="Attendance access required"><Screen /></RequirePermission></Page>;
}
