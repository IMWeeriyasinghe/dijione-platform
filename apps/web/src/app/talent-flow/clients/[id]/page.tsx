"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { use } from "react";
import { getClient, listTalentRequests } from "@/lib/api";
import { ErrorState, LoadingState, EmptyState } from "@/components/ui/States";
import { Card, CardContent } from "@/components/ui/Card";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { RequestCard } from "@/components/talent/RequestCard";
import { formatDate } from "@/lib/utils";

export default function ClientPortfolioDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const clientId = Number(id);

  const clientQuery = useQuery({ queryKey: ["client", clientId], queryFn: () => getClient(clientId) });
  const requestsQuery = useQuery({
    queryKey: ["talent-requests", "by-client", clientId],
    queryFn: () => listTalentRequests({ client_id: clientId }),
  });

  if (clientQuery.isLoading || requestsQuery.isLoading) return <LoadingState label="Loading client…" />;
  if (clientQuery.isError || !clientQuery.data) return <ErrorState onRetry={() => clientQuery.refetch()} />;

  const client = clientQuery.data;

  return (
    <div>
      <Link
        href="/talent-flow/clients"
        className="mb-4 inline-flex items-center gap-1.5 text-sm text-dt-text-secondary hover:text-dt-text-primary"
      >
        <ArrowLeft className="size-4" />
        Back to client portfolios
      </Link>

      <Card className="mb-6">
        <CardContent className="pt-5">
          <div className="flex items-start justify-between gap-4">
            <div>
              <h1 className="text-xl font-semibold text-dt-text-primary">{client.name}</h1>
              <p className="text-sm text-dt-text-secondary">{client.industry || "—"}</p>
            </div>
            <StatusBadge status={client.status} />
          </div>
          <dl className="mt-4 grid grid-cols-2 gap-3 text-sm sm:grid-cols-3">
            <div>
              <dt className="text-dt-text-secondary">Account Manager</dt>
              <dd className="font-medium text-dt-text-primary">{client.account_manager || "—"}</dd>
            </div>
            <div>
              <dt className="text-dt-text-secondary">Client Since</dt>
              <dd className="font-medium text-dt-text-primary">{formatDate(client.created_at)}</dd>
            </div>
          </dl>
        </CardContent>
      </Card>

      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-dt-text-secondary">
        Talent Requests
      </h2>
      {requestsQuery.data && requestsQuery.data.length === 0 && (
        <EmptyState title="No requests yet" description="This client has not submitted any talent requests." />
      )}
      {requestsQuery.data && requestsQuery.data.length > 0 && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {requestsQuery.data.map((r) => (
            <RequestCard key={r.id} request={r} />
          ))}
        </div>
      )}
    </div>
  );
}
