"use client";

import { useQuery } from "@tanstack/react-query";
import { Building2, LayoutGrid, TableIcon } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { listClientPortfolios } from "@/lib/api";
import type { ClientPortfolioOut } from "@dijione/contracts";
import { PageHeader } from "@dijione/design-system";
import { Table, Thead, Th, Tr, Td } from "@dijione/design-system";
import { Card } from "@dijione/design-system";
import { StatusBadge } from "@dijione/design-system";
import { EmptyState, ErrorState, LoadingState } from "@dijione/design-system";
import { formatDate } from "@dijione/design-system";

// Industry / Account Manager are intentionally not shown: ClientOut still
// carries them (real, nullable columns), but nothing in this codebase
// populates them for the real DTC-verified client set yet — every row
// would just render "—". Bring the columns back once a real source
// exists rather than showing an always-empty field.

function ClientCard({ c }: { c: ClientPortfolioOut }) {
  return (
    <Card className="relative flex h-full flex-col gap-3 p-5 transition hover:-translate-y-0.5 hover:shadow-md">
      {/* Stretched-link pattern: the whole card is clickable to the client
          detail page, while the two stat links below remain independently
          clickable (they sit above this overlay in stacking order) — no
          invalid nested <a> elements. */}
      <Link href={`/clients/${c.id}`} className="absolute inset-0 z-0" aria-label={c.name} />

      <div className="relative z-10 flex items-start justify-between gap-3">
        <p className="text-base font-semibold text-dt-text-primary">{c.name}</p>
        <StatusBadge status={c.status} />
      </div>

      <div className="relative z-10 flex flex-wrap items-center gap-x-1.5 gap-y-1 text-sm text-dt-text-secondary">
        <Link
          href={`/requests?client_id=${c.id}`}
          className="font-medium text-dt-text-primary hover:text-dt-burnt-orange hover:underline"
        >
          {c.total_requests} request{c.total_requests === 1 ? "" : "s"}
        </Link>
        <span>·</span>
        <Link
          href={`/requests?client_id=${c.id}&status=active`}
          className="font-medium text-dt-text-primary hover:text-dt-burnt-orange hover:underline"
        >
          {c.active_requests} active
        </Link>
      </div>

      {/* Not a link: no view currently supports filtering applications by
          (client + client-visible) without a backend addition — showing
          the real number beats linking somewhere misleading. */}
      <p className="relative z-10 text-sm text-dt-text-secondary">
        <span className="font-medium text-dt-text-primary">{c.client_visible_count}</span> shared with client
        {c.active_application_count > 0 && (
          <span className="text-dt-text-secondary"> · {c.active_application_count} in active pipeline</span>
        )}
      </p>

      <p className="relative z-10 mt-auto text-xs text-dt-text-secondary">
        {c.latest_request_at ? `Latest request: ${formatDate(c.latest_request_at)}` : "No requests yet"}
      </p>
    </Card>
  );
}

export default function ClientPortfoliosPage() {
  const [view, setView] = useState<"cards" | "table">("cards");
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["client-portfolios"],
    queryFn: listClientPortfolios,
  });

  return (
    <div>
      <div className="mb-6 flex flex-wrap items-start justify-between gap-3">
        <PageHeader title="Client Portfolios" description="Every Dijital Team client tracked in DijiTalentFlow." />
        <div className="flex gap-1 rounded-lg border border-dt-border bg-dt-surface p-1">
          <button
            type="button"
            onClick={() => setView("cards")}
            aria-pressed={view === "cards"}
            className={`flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs font-medium ${
              view === "cards" ? "bg-dt-surface-warm text-dt-burnt-orange" : "text-dt-text-secondary"
            }`}
          >
            <LayoutGrid className="size-3.5" />
            Cards
          </button>
          <button
            type="button"
            onClick={() => setView("table")}
            aria-pressed={view === "table"}
            className={`flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs font-medium ${
              view === "table" ? "bg-dt-surface-warm text-dt-burnt-orange" : "text-dt-text-secondary"
            }`}
          >
            <TableIcon className="size-3.5" />
            Table
          </button>
        </div>
      </div>

      {isLoading && <LoadingState label="Loading clients…" />}
      {isError && <ErrorState onRetry={() => refetch()} />}
      {data && data.length === 0 && <EmptyState icon={Building2} title="No clients yet" />}

      {data && data.length > 0 && view === "cards" && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {data.map((c) => (
            <ClientCard key={c.id} c={c} />
          ))}
        </div>
      )}

      {data && data.length > 0 && view === "table" && (
        <Table>
          <Thead>
            <tr>
              <Th>Client</Th>
              <Th>Total Requests</Th>
              <Th>Active Requests</Th>
              <Th>Shared with Client</Th>
              <Th>Latest Request</Th>
              <Th>Status</Th>
            </tr>
          </Thead>
          <tbody>
            {data.map((c) => (
              <Tr key={c.id}>
                <Td className="font-medium">
                  <Link href={`/clients/${c.id}`} className="hover:text-dt-burnt-orange">
                    {c.name}
                  </Link>
                </Td>
                <Td>
                  <Link href={`/requests?client_id=${c.id}`} className="hover:text-dt-burnt-orange">
                    {c.total_requests}
                  </Link>
                </Td>
                <Td>
                  <Link
                    href={`/requests?client_id=${c.id}&status=active`}
                    className="hover:text-dt-burnt-orange"
                  >
                    {c.active_requests}
                  </Link>
                </Td>
                <Td>{c.client_visible_count}</Td>
                <Td>{c.latest_request_at ? formatDate(c.latest_request_at) : "—"}</Td>
                <Td>
                  <StatusBadge status={c.status} />
                </Td>
              </Tr>
            ))}
          </tbody>
        </Table>
      )}
    </div>
  );
}
