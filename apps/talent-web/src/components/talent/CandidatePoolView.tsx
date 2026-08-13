"use client";

import { useQuery } from "@tanstack/react-query";
import { Plus, Search, UserRound } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { listCandidates } from "@/lib/api";
import { PageHeader } from "@dijione/design-system";
import { Button } from "@dijione/design-system";
import { Card } from "@dijione/design-system";
import { StatusBadge } from "@dijione/design-system";
import { EmptyState, ErrorState, LoadingState } from "@dijione/design-system";
import { CreateCandidateModal } from "./CreateCandidateModal";

export function CandidatePoolView() {
  const [search, setSearch] = useState("");
  const [createOpen, setCreateOpen] = useState(false);
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["candidates", search],
    queryFn: () => listCandidates(search || undefined),
  });

  return (
    <div>
      <PageHeader
        title="Candidate Pool"
        description="One master profile per candidate, reusable across every client (CLAUDE.md §19)."
        action={
          <Button onClick={() => setCreateOpen(true)}>
            <Plus className="size-4" />
            Add Candidate
          </Button>
        }
      />

      <div className="relative mb-6 max-w-md">
        <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-dt-text-secondary" />
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search by name or title…"
          className="w-full rounded-lg border border-dt-border bg-dt-surface py-2 pl-9 pr-3 text-sm focus:border-dt-orange focus:outline-none focus:ring-2 focus:ring-dt-orange/20"
        />
      </div>

      {isLoading && <LoadingState label="Loading candidates…" />}
      {isError && <ErrorState onRetry={() => refetch()} />}
      {data && data.length === 0 && (
        <EmptyState icon={UserRound} title="No candidates found" description="Try a different search, or add a new candidate." />
      )}
      {data && data.length > 0 && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {data.map((c) => (
            <Link key={c.id} href={`/candidates/${c.id}`}>
              <Card className="flex h-full flex-col gap-3 p-5 transition hover:-translate-y-0.5 hover:shadow-md">
                <div>
                  <p className="text-base font-semibold text-dt-text-primary">{c.full_name}</p>
                  <p className="text-sm text-dt-text-secondary">{c.professional_title || "—"}</p>
                </div>
                <StatusBadge status={c.availability_status} />
                <div className="flex flex-wrap gap-1.5">
                  {c.skills.slice(0, 4).map((s) => (
                    <span key={s} className="rounded-full bg-dt-surface-warm px-2 py-0.5 text-xs text-dt-text-primary">
                      {s}
                    </span>
                  ))}
                </div>
                <p className="mt-auto text-xs text-dt-text-secondary">
                  {c.applications.length} application{c.applications.length === 1 ? "" : "s"}
                </p>
              </Card>
            </Link>
          ))}
        </div>
      )}

      <CreateCandidateModal open={createOpen} onClose={() => setCreateOpen(false)} />
    </div>
  );
}
