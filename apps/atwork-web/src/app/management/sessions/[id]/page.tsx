"use client";

import Link from "next/link";
import { use } from "react";
import { useQuery } from "@tanstack/react-query";
import { LoadingState, PageHeader } from "@dijione/design-system";
import { Page, QueryError, RequirePermission, SessionBadge, SessionDetails } from "@/components/ui";
import { management } from "@/lib/api";
import { hasPermission, PERM, useAtworkScope } from "@/lib/atwork-scope";
import { useDisplay } from "@/lib/hooks";

function Screen({ id }: { id: string }) {
  const { scope } = useAtworkScope();
  const { format } = useDisplay();
  const query = useQuery({ queryKey: ["atwork", "managed-session", id], queryFn: () => management.session(id), retry: false });
  if (query.isLoading) return <LoadingState />;
  if (!query.data) return <QueryError error={query.error} retry={() => query.refetch()} />;
  const { employee, session } = query.data;
  return (
    <>
      <PageHeader title={employee.employee_name} description="Attendance session" />
      <div className="mb-4"><SessionBadge session={session} /></div>
      <SessionDetails session={session} zone={session.time_zone} format={format} />
      <p className="mt-6 flex flex-wrap gap-4 text-sm font-medium text-dt-burnt-orange">
        <Link className="underline underline-offset-2" href={`/management/employees/${employee.platform_user_id}`}>Back to employee</Link>
        {hasPermission(scope, PERM.AUDIT) && <Link className="underline underline-offset-2" href={`/management/audit?session=${session.id}`}>View audit history</Link>}
      </p>
    </>
  );
}

export default function ManagedSessionPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  return <Page><RequirePermission permission={[PERM.MANAGEMENT, PERM.READ_ALL]} title="Attendance visibility required"><Screen id={id} /></RequirePermission></Page>;
}
