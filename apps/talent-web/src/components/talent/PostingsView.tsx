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

export function PostingsView() {
  const qc = useQueryClient();
  const [needsReviewOnly, setNeedsReviewOnly] = useState(false);
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

  const rows = needsReviewOnly
    ? postings.data.filter(
        (p) => p.mapping_status !== "VERIFIED" && NEEDS_REVIEW.has(p.resolution_status),
      )
    : postings.data;

  return (
    <div>
      <PageHeader
        title="Recruitment Postings"
        description="Lever job postings and their client mapping. A posting becomes visible to a client only once its 'DTC - <Client>' tag resolves to a verified client — or a staff member verifies it manually."
      />

      <label className="mb-4 flex items-center gap-2 text-sm text-dt-text-secondary">
        <input
          type="checkbox"
          checked={needsReviewOnly}
          onChange={(e) => setNeedsReviewOnly(e.target.checked)}
        />
        Needs review only
      </label>

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
