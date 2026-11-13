"use client";

import { Button } from "@dijione/design-system";
import {
  EmptyState,
  ErrorState,
  LoadingState,
  Modal,
  PageHeader,
  Select,
  Table,
  Td,
  Th,
  Thead,
  Tr,
  formatDate,
} from "@dijione/design-system";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { TABLE_PAGE_SIZES, keepPageWhile, usePaging } from "@/lib/paging";
import { TalentPagination } from "./TalentPagination";
import {
  type PostingRow,
  type PostingView,
  listClientPortfolios,
  listRecruitmentPostingsPaged,
  reopenPostingMapping,
  unmapPostingMapping,
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
  danger: "bg-dt-cream text-dt-danger",
} as const;

// Four visible states (plan §G2), all already representable by the
// existing status/source columns — this only labels them:
//   Auto-verified     VERIFIED / LEVER_DTC_TAG  — DTC-managed
//   Manually verified VERIFIED / MANUAL         — DTC never overwrites
//   Manually unmapped REJECTED / MANUAL         — reconciler-immune
//   Unmapped          UNMAPPED / ""             — DTC will resolve it
function mappingLabel(p: PostingRow): { text: string; tone: keyof typeof TONE_CLASS } {
  if (p.mapping_status === "VERIFIED" && p.mapping_source === "MANUAL") {
    return { text: "Manually verified", tone: "success" };
  }
  if (p.mapping_status === "VERIFIED") return { text: "Auto-verified", tone: "success" };
  if (p.mapping_status === "REJECTED") return { text: "Manually unmapped", tone: "danger" };
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
// The filters are applied server-side (/postings/paged ?view=…) with the
// same definitions this page used to apply in the browser; ``counts`` gives
// every chip's total for the current authorized scope.
type PostingFilter = PostingView;

const FILTERS: { key: PostingFilter; label: string }[] = [
  { key: "active", label: "Recent / Active" },
  { key: "verified", label: "Verified" },
  { key: "unmapped", label: "Unmapped" },
  { key: "review", label: "Needs review" },
  { key: "all", label: "All" },
];

export function PostingsView() {
  const qc = useQueryClient();
  const [filter, setFilter] = useState<PostingFilter>("active");
  const paging = usePaging(TABLE_PAGE_SIZES[0]);
  const [verifyingId, setVerifyingId] = useState<number | null>(null);
  const [pickClientId, setPickClientId] = useState<number | null>(null);
  const [unmapTarget, setUnmapTarget] = useState<PostingRow | null>(null);

  const postings = useQuery({
    queryKey: ["recruitment-postings", "paged", filter, paging.page, paging.pageSize],
    queryFn: () =>
      listRecruitmentPostingsPaged({ view: filter, page: paging.page, page_size: paging.pageSize }),
    placeholderData: keepPageWhile((k) => k[2] === filter),
  });
  const clients = useQuery({ queryKey: ["client-portfolios"], queryFn: listClientPortfolios });

  function invalidate() {
    qc.invalidateQueries({ queryKey: ["recruitment-postings"] });
  }

  const verify = useMutation({
    mutationFn: ({ id, clientId }: { id: number; clientId: number }) =>
      verifyPostingMapping(id, clientId),
    onSuccess: () => {
      setVerifyingId(null);
      setPickClientId(null);
      invalidate();
    },
  });

  const unmap = useMutation({
    mutationFn: (id: number) => unmapPostingMapping(id),
    onSuccess: () => {
      setUnmapTarget(null);
      invalidate();
    },
  });

  const reopen = useMutation({
    mutationFn: (id: number) => reopenPostingMapping(id),
    onSuccess: invalidate,
  });

  if (postings.isLoading) return <LoadingState label="Loading recruitment postings…" />;
  if (!postings.data) return <ErrorState onRetry={() => postings.refetch()} />;

  const page = postings.data;
  const rows = page.items;

  return (
    <div>
      <PageHeader
        title="Recruitment Postings"
        description="Lever job postings and their client mapping. A posting becomes visible to a client only once its 'DTC - <Client>' tag resolves to a verified client — or a staff member verifies it manually."
      />

      <div className="mb-2 flex flex-wrap gap-2">
        {FILTERS.map((f) => {
          const count = page.counts[f.key];
          const active = filter === f.key;
          return (
            <button
              key={f.key}
              type="button"
              aria-pressed={active}
              onClick={() => {
                setFilter(f.key);
                paging.reset();
              }}
              className={
                active
                  ? "rounded-full border border-dt-orange bg-dt-cream px-3 py-1 text-xs font-medium text-dt-burnt-orange"
                  : "rounded-full border border-dt-border px-3 py-1 text-xs text-dt-text-secondary hover:border-dt-orange"
              }
            >
              {f.label} <span>({count})</span>
            </button>
          );
        })}
      </div>
      <p className="mb-4 text-xs text-dt-text-secondary">
        {filter === "active" && page.counts.all > page.counts.active
          ? `${page.counts.all - page.counts.active} closed/older postings hidden (use "All")`
          : " "}
      </p>

      {page.total === 0 ? (
        <EmptyState title="Nothing here" description="No postings match the current filter." />
      ) : rows.length === 0 ? (
        <p className="mb-4 text-sm text-dt-text-secondary">
          This page is now empty — the list has changed.{" "}
          <button type="button" className="underline" onClick={() => paging.setPage(page.total_pages)}>
            Go to the last page
          </button>
        </p>
      ) : (
        <div
          aria-busy={postings.isFetching}
          className={`overflow-x-auto${postings.isFetching ? " opacity-70 transition-opacity" : ""}`}
        >
          <Table>
            <Thead>
              <Tr>
                <Th>Posting</Th>
                <Th>Created</Th>
                <Th>Lever client tag</Th>
                <Th>Resolved client</Th>
                <Th>Mapping</Th>
                <Th>Action</Th>
              </Tr>
            </Thead>
            <tbody>
              {rows.map((p) => {
                const m = mappingLabel(p);
                const isVerified = p.mapping_status === "VERIFIED";
                const isManuallyUnmapped = p.mapping_status === "REJECTED";
                return (
                  <Tr key={p.id}>
                    <Td>
                      <div className="font-medium text-dt-text-primary">{p.title}</div>
                      <div className="text-xs text-dt-text-secondary">{p.state}</div>
                    </Td>
                    <Td className="whitespace-nowrap text-xs text-dt-text-secondary">
                      {p.lever_created_at ? formatDate(p.lever_created_at) : "—"}
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
                            aria-label="Client for this posting"
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
                      ) : isManuallyUnmapped ? (
                        <Button
                          size="sm"
                          variant="secondary"
                          disabled={reopen.isPending}
                          onClick={() => reopen.mutate(p.id)}
                        >
                          Reopen
                        </Button>
                      ) : (
                        <div className="flex items-center gap-2">
                          <Button
                            size="sm"
                            variant="secondary"
                            onClick={() => {
                              setVerifyingId(p.id);
                              setPickClientId(p.mapping_client_id ?? null);
                            }}
                          >
                            {isVerified ? "Change" : "Verify manually"}
                          </Button>
                          {isVerified && (
                            <Button size="sm" variant="ghost" onClick={() => setUnmapTarget(p)}>
                              Unmap
                            </Button>
                          )}
                        </div>
                      )}
                    </Td>
                  </Tr>
                );
              })}
            </tbody>
          </Table>
        </div>
      )}

      {postings.isError && (
        <p role="alert" className="mt-4 text-sm text-dt-danger">
          Couldn&apos;t load that page.{" "}
          <button type="button" className="underline" onClick={() => postings.refetch()}>
            Try again
          </button>
        </p>
      )}
      {page.total > 0 && (
        <TalentPagination
          page={Math.min(paging.page, page.total_pages)}
          pageSize={paging.pageSize}
          pageSizes={TABLE_PAGE_SIZES}
          total={page.total}
          totalPages={page.total_pages}
          onPageChange={(p) => {
            paging.setPage(p);
            window.scrollTo({ top: 0, behavior: "smooth" });
          }}
          onPageSizeChange={paging.setPageSize}
          noun={["posting", "postings"]}
        />
      )}

      <Modal open={unmapTarget !== null} onClose={() => setUnmapTarget(null)} title="Remove client mapping?">
        <p className="text-sm text-dt-text-secondary">
          <span className="font-medium text-dt-text-primary">{unmapTarget?.title}</span> will stop being
          visible to {unmapTarget?.mapping_client_name ?? "its current client"}. This does not change
          anything in Lever, and can be undone with Reopen. The next sync will not re-verify it — DTC
          reconciliation never overrides a manually unmapped posting.
        </p>
        <div className="mt-5 flex justify-end gap-2">
          <Button variant="ghost" onClick={() => setUnmapTarget(null)}>
            Cancel
          </Button>
          <Button
            variant="secondary"
            disabled={unmap.isPending}
            onClick={() => unmapTarget && unmap.mutate(unmapTarget.id)}
          >
            {unmap.isPending ? "Unmapping…" : "Unmap"}
          </Button>
        </div>
      </Modal>
    </div>
  );
}
