"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { listAdminModules } from "@/lib/api";
import { PageHeader } from "@dijione/design-system";
import { Card } from "@dijione/design-system";
import { StatusBadge } from "@dijione/design-system";
import { ModuleIcon } from "@/lib/module-icons";
import { LoadingState, ErrorState } from "@dijione/design-system";

export default function AdminApplicationsPage() {
  const query = useQuery({ queryKey: ["admin", "modules"], queryFn: listAdminModules });

  return (
    <div>
      <PageHeader
        title="Applications"
        description="The DijiOne module registry. DijiTalentFlow is fully implemented; DijiBirthday and DijiSpark are registered as Coming Soon placeholders and do not expose functional workflows yet."
      />
      {query.isLoading && <LoadingState label="Loading applications…" />}
      {query.isError && <ErrorState message="Could not load applications." onRetry={() => query.refetch()} />}
      {query.data && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {query.data.map((m) => (
            <Link key={m.key} href={`/applications/${m.key}`}>
              <Card className="h-full p-5 transition hover:border-dt-orange/40 hover:shadow-md">
                <div className="mb-3 flex items-center justify-between">
                  <div className="flex size-11 items-center justify-center rounded-2xl bg-linear-to-br from-dt-red to-dt-orange text-white">
                    <ModuleIcon iconKey={m.icon} className="size-5" />
                  </div>
                  <StatusBadge status={m.status} />
                </div>
                <p className="text-base font-semibold text-dt-text-primary">{m.name}</p>
                <p className="mt-1 text-sm text-dt-text-secondary">{m.description}</p>
                <div className="mt-4 flex items-center justify-between text-xs text-dt-text-secondary">
                  <span>Key: {m.key}</span>
                  <span>{m.user_count} assigned user{m.user_count === 1 ? "" : "s"}</span>
                </div>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
