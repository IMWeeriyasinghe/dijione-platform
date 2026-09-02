"use client";

import { Button } from "@dijione/design-system";
import {
  EmptyState,
  ErrorState,
  LoadingState,
  PageHeader,
  Select,
  Table,
  Td,
  Th,
  Thead,
  Tr,
} from "@dijione/design-system";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import {
  type PostingRow,
  listClientPortfolios,
  listRecruitmentPostings,
  verifyPostingMapping,
} from "@/lib/api";

const NEEDS_REVIEW = new Set([
  "UNKNOWN_CLIENT_IDENTIFIER",
  "AMBIGUOUS_MULTIPLE_TAGS",
  "AMBIGUOUS_CLIENT_NAME",
  "MALFORMED_TAG",
  "CONFLICT_MANUAL_OVERRIDE",
]);

const TONE_CLASS = {
  success: "bg-dt-cream text-dt-success",
  warning: "bg-dt-cream text-dt-warning",
  neutral: "bg-dt-surface-warm text-dt-text-secondary",
} as const;

function mappingLabel(p: PostingRow): { text: string; tone: keyof typeof TONE_CLASS } {
  if (p.mapping_status === "VERIFIED") return { text: "Mapped", tone: "success" };
  if (NEEDS_REVIEW.has(p.resolution_status)) return { text: "Needs review", tone: "warning" };
  return { text: "Unmapped", tone: "neutral" };
}

function Badge({ tone, children }: { tone: keyof typeof TONE_CLASS; children: React.ReactNode }) {
  return (
    <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${TONE_CLASS[tone]}`}>
      {children}
    </span>
  );
}

// The Recruitment Source read model carries ~3.5 years of Lever history —
// the large majority are old `closed` postings with no DTC tag, which is
// correct fail-closed behaviour but useless as a default TA view. Default
// to what a TA acts on now; every other cut stays one click away, and
// "All" is an explicit escape hatch (nothing is hidden from diagnosis).
type PostingFilter = "active" | "verified" | "unmapped" | "review" | "all";

const FILTERS: { key: PostingFilter; label: string; match: (p: PostingRow) => boolean }[] = [
  { key: "active", label: "Recent / Active", match: (p) => p.state !== "closed" },
  { key: "verified", label: "Verified", match: (p) => p.mapping_status === "VERIFIED" },
  { key: "unmapped", label: "Unmapped", match: (p) => p.mapping_status === "UNMAPPED" },
  {
    key: "review",
    label: "Needs review",
    match: (p) => p.mapping_status !== "VERIFIED" && NEEDS_REVIEW.has(p.resolution_status),
  },
  { key: "all", label: "All", match: () => true },
];

export function PostingsView() {
  const qc = useQueryClient();
  const [filter, setFilter] = useState<PostingFilter>("active");
  const [verifyingId, setVerifyingId] = useState<number | null>(null);
  const [pickClientId, setPickClientId] = useState<number | null>(null);

  const postings = useQuery({
    queryKey: ["recruitment-postings"],
    queryFn: () => listRecruitmentPostings(),
  });
  const clients = useQuery({ queryKey: ["client-portfolios"], queryFn: listClientPortfolios });

  const verify = useMutation({
    mutationFn: ({ id, clientId }: { id: number; clientId: number }) =>
      verifyPostingMapping(id, clientId),
    onSuccess: () => {
      setVerifyingId(null);
      setPickClientId(null);
      qc.invalidateQueries({ queryKey: ["recruitment-postings"] });
    },
  });

  if (postings.isLoading) return <LoadingState label="Loading recruitment postings…" />;
  if (postings.isError || !postings.data)
    return <ErrorState onRetry={() => postings.refetch()} />;

  const all = postings.data;
  const rows = all.filter(FILTERS.find((f) => f.key === filter)!.match);

  return (
    <div>
      <PageHeader
        title="Recruitment Postings"
        description="Lever job postings and their client mapping. A posting becomes visible to a client only once its 'DTC - <Client>' tag resolves to a verified client — or a staff member verifies it manually."
      />

      <div className="mb-2 flex flex-wrap gap-2">
        {FILTERS.map((f) => {
          const count = all.filter(f.match).length;
          const active = filter === f.key;
          return (
            <button
              key={f.key}
              type="button"
              onClick={() => setFilter(f.key)}
              className={
                active
                  ? "rounded-full border border-dt-orange bg-dt-cream px-3 py-1 text-xs font-medium text-dt-burnt-orange"
                  : "rounded-full border border-dt-border px-3 py-1 text-xs text-dt-text-secondary hover:border-dt-orange"
              }
            >
              {f.label} <span className="opacity-60">({count})</span>
            </button>
          );
        })}
      </div>
      <p className="mb-4 text-xs text-dt-text-secondary">
        Showing {rows.length} of {all.length} postings
        {filter === "active" && all.length > rows.length
          ? ` — ${all.length - rows.length} closed/older hidden (use "All")`
          : ""}
      </p>

      {rows.length === 0 ? (
        <EmptyState title="Nothing here" description="No postings match the current filter." />
      ) : (
        <div className="overflow-x-auto">
          <Table>
            <Thead>
              <Tr>
                <Th>Posting</Th>
                <Th>Lever client tag</Th>
                <Th>Resolved client</Th>
                <Th>Mapping</Th>
                <Th>Action</Th>
              </Tr>
            </Thead>
            <tbody>
              {rows.map((p) => {
                const m = mappingLabel(p);
                return (
                  <Tr key={p.id}>
                    <Td>
                      <div className="font-medium text-dt-text-primary">{p.title}</div>
                      <div className="text-xs text-dt-text-secondary">{p.state}</div>
                    </Td>
                    <Td>{p.dtc_source_tag ?? <span className="text-dt-text-secondary">Not supplied</span>}</Td>
                    <Td>{p.mapping_client_name ?? "—"}</Td>
                    <Td>
                      <Badge tone={m.tone}>{m.text}</Badge>
                      {m.text === "Needs review" && (
                        <div className="mt-1 text-xs text-dt-warning">{p.resolution_status}</div>
                      )}
                    </Td>
                    <Td>
                      {verifyingId === p.id ? (
                        <div className="flex items-center gap-2">
                          <Select
                            value={pickClientId ?? ""}
                            onChange={(e) => setPickClientId(Number(e.target.value) || null)}
                          >
                            <option value="">Choose client…</option>
                            {(clients.data ?? []).map((c) => (
                              <option key={c.id} value={c.id}>
                                {c.name}
                              </option>
                            ))}
                          </Select>
                          <Button
                            size="sm"
                            disabled={!pickClientId || verify.isPending}
                            onClick={() =>
                              pickClientId && verify.mutate({ id: p.id, clientId: pickClientId })
                            }
                          >
                            Save
                          </Button>
                          <Button size="sm" variant="ghost" onClick={() => setVerifyingId(null)}>
                            Cancel
                          </Button>
                        </div>
                      ) : (
                        <Button
                          size="sm"
                          variant="secondary"
                          onClick={() => {
                            setVerifyingId(p.id);
                            setPickClientId(p.mapping_client_id ?? null);
                          }}
                        >
                          Verify manually
                        </Button>
                      )}
                    </Td>
                  </Tr>
                );
              })}
            </tbody>
          </Table>
        </div>
      )}
    </div>
  );
}
