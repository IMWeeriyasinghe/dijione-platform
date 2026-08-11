"use client";

import { useQuery } from "@tanstack/react-query";
import { MessageSquare } from "lucide-react";
import Link from "next/link";
import { listMessages, listTalentRequests } from "@/lib/api";
import { PageHeader } from "@/components/ui/PageHeader";
import { Card } from "@/components/ui/Card";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/States";
import { formatDateTime } from "@/lib/utils";

export default function MessagesOverviewPage() {
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["messages-overview"],
    queryFn: async () => {
      const requests = await listTalentRequests();
      const withMessages = await Promise.all(
        requests.map(async (r) => ({ request: r, messages: await listMessages(r.id) }))
      );
      return withMessages
        .filter((w) => w.messages.length > 0)
        .sort(
          (a, b) =>
            new Date(b.messages.at(-1)!.created_at).getTime() -
            new Date(a.messages.at(-1)!.created_at).getTime()
        );
    },
  });

  return (
    <div>
      <PageHeader title="Messages" description="Conversations with Dijital Team about your talent requests." />

      {isLoading && <LoadingState label="Loading conversations…" />}
      {isError && <ErrorState onRetry={() => refetch()} />}
      {data && data.length === 0 && (
        <EmptyState
          icon={MessageSquare}
          title="No conversations yet"
          description="Messages tied to your talent requests will appear here."
        />
      )}

      {data && data.length > 0 && (
        <div className="flex flex-col gap-3">
          {data.map(({ request, messages }) => {
            const last = messages.at(-1)!;
            return (
              <Link key={request.id} href={`/talent-flow/requests/${request.id}?tab=messages`}>
                <Card className="flex items-center gap-4 p-4 transition hover:-translate-y-0.5 hover:shadow-md">
                  <div className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-dt-surface-warm text-dt-burnt-orange">
                    <MessageSquare className="size-4.5" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-semibold text-dt-text-primary">
                      {request.designation} <span className="font-normal text-dt-text-secondary">({request.request_code})</span>
                    </p>
                    <p className="truncate text-sm text-dt-text-secondary">
                      {last.sender_name}: {last.body}
                    </p>
                  </div>
                  <p className="shrink-0 text-xs text-dt-text-secondary">{formatDateTime(last.created_at)}</p>
                </Card>
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}
