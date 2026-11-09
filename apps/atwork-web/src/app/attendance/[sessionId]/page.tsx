"use client";

import Link from "next/link";
import { use } from "react";
import { useQuery } from "@tanstack/react-query";
import { Button, LoadingState, PageHeader } from "@dijione/design-system";
import { Page, QueryError, RequirePermission, SessionBadge, SessionDetails } from "@/components/ui";
import { attendance } from "@/lib/api";
import { hasPermission, PERM, useAtworkScope } from "@/lib/atwork-scope";
import { useDisplay } from "@/lib/hooks";

function Detail({ id }: { id: string }) {
  const { scope } = useAtworkScope();
  const { format } = useDisplay();
  const query = useQuery({ queryKey: ["atwork", "session", id], queryFn: () => attendance.session(id), retry: false });
  if (query.isLoading) return <LoadingState />;
  if (!query.data) return <QueryError error={query.error} retry={() => query.refetch()} />;
  const s = query.data;
  return (
    <>
      <PageHeader title="Session details" action={hasPermission(scope, PERM.REQUEST_OWN) ? <Link href={`/requests/new?sessionId=${s.id}`}><Button variant="secondary">Request correction</Button></Link> : undefined} />
      <div className="mb-4"><SessionBadge session={s} /></div>
      <SessionDetails session={s} zone={s.time_zone} format={format} />
      <Link href="/attendance" className="mt-6 inline-block text-sm font-medium text-dt-burnt-orange underline underline-offset-2">Back to My Attendance</Link>
    </>
  );
}

export default function SessionPage({ params }: { params: Promise<{ sessionId: string }> }) {
  const { sessionId } = use(params);
  return <Page><RequirePermission permission={PERM.READ_OWN} title="Attendance access required"><Detail id={sessionId} /></RequirePermission></Page>;
}
