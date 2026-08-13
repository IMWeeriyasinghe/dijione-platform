"use client";

import { useQuery } from "@tanstack/react-query";
import { FileText } from "lucide-react";
import Link from "next/link";
import { listDocuments, listTalentRequests } from "@/lib/api";
import { PageHeader } from "@dijione/design-system";
import { Card } from "@dijione/design-system";
import { EmptyState, ErrorState, LoadingState } from "@dijione/design-system";
import { formatDate } from "@dijione/design-system";

export default function DocumentsOverviewPage() {
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["documents-overview"],
    queryFn: async () => {
      const requests = await listTalentRequests();
      const withDocs = await Promise.all(
        requests.map(async (r) => ({ request: r, documents: await listDocuments(r.id) }))
      );
      return withDocs.filter((w) => w.documents.length > 0);
    },
  });

  return (
    <div>
      <PageHeader title="Documents" description="Files shared across all of your talent requests." />

      {isLoading && <LoadingState label="Loading documents…" />}
      {isError && <ErrorState onRetry={() => refetch()} />}
      {data && data.length === 0 && (
        <EmptyState icon={FileText} title="No documents yet" description="Documents added to your requests will appear here." />
      )}

      {data && data.length > 0 && (
        <div className="flex flex-col gap-8">
          {data.map(({ request, documents }) => (
            <section key={request.id}>
              <Link
                href={`/requests/${request.id}?tab=documents`}
                className="mb-3 inline-block text-sm font-semibold text-dt-text-primary hover:text-dt-burnt-orange"
              >
                {request.designation} <span className="text-dt-text-secondary">({request.request_code})</span>
              </Link>
              <div className="grid gap-3 sm:grid-cols-2">
                {documents.map((doc) => (
                  <Card key={doc.id} className="flex items-center gap-3 p-4">
                    <div className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-dt-surface-warm text-dt-burnt-orange">
                      <FileText className="size-4.5" />
                    </div>
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium text-dt-text-primary">{doc.file_name}</p>
                      <p className="text-xs text-dt-text-secondary">
                        {doc.category.replace("_", " ")} · {formatDate(doc.created_at)}
                      </p>
                    </div>
                  </Card>
                ))}
              </div>
            </section>
          ))}
        </div>
      )}
    </div>
  );
}
