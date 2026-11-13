"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useCallback, useState } from "react";

/** A bounded picker: the pool can hold thousands of Lever candidates, so
 * the list is a server-side search showing the top matches, never the
 * whole pool. */
export const PICKER_LIMIT = 24;
import { ApiError, createApplication, listCandidatesPaged } from "@/lib/api";
import { useDebouncedSearch } from "@/lib/paging";
import { Modal } from "@/components/talent/Modal";
import { Button } from "@dijione/design-system";
import { FormField, Select } from "@dijione/design-system";
import { CANONICAL_STAGES } from "@dijione/contracts";
import { stageLabel } from "@dijione/design-system";

export function AddApplicationModal({
  requestId,
  open,
  onClose,
}: {
  requestId: number;
  open: boolean;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [candidateId, setCandidateId] = useState<string>("");
  const clearSelection = useCallback(() => setCandidateId(""), []);
  const { input, setInput, search } = useDebouncedSearch(clearSelection);
  const { data: page, isFetching } = useQuery({
    queryKey: ["candidates", "picker", search],
    queryFn: () => listCandidatesPaged({ search: search || undefined, page: 1, page_size: PICKER_LIMIT }),
    enabled: open,
  });
  const candidates = page?.items;
  const [stage, setStage] = useState<string>(CANONICAL_STAGES[2]);
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: () =>
      createApplication({ candidate_id: Number(candidateId), talent_request_id: requestId, current_stage: stage }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["applications", requestId] });
      queryClient.invalidateQueries({ queryKey: ["talent-request", requestId] });
      setCandidateId("");
      onClose();
    },
    onError: (err) =>
      setError(err instanceof ApiError ? err.message : "Could not link this candidate to the request."),
  });

  return (
    <Modal open={open} onClose={onClose} title="Add Candidate to Request">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          setError(null);
          if (!candidateId) {
            setError("Select a candidate first.");
            return;
          }
          mutation.mutate();
        }}
        className="flex flex-col gap-4"
      >
        <FormField label="Find candidate" htmlFor="candidate-search">
          <input
            id="candidate-search"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Search by name or title…"
            className="w-full rounded-lg border border-dt-border bg-dt-surface px-3 py-2 text-sm focus:border-dt-orange focus:outline-none focus:ring-2 focus:ring-dt-orange/20"
          />
          {page && page.total > PICKER_LIMIT && (
            <p className="mt-1 text-xs text-dt-text-secondary" aria-live="polite">
              Showing the first {PICKER_LIMIT} of {page.total.toLocaleString()} matches — refine your search to narrow the list.
            </p>
          )}
        </FormField>
        <FormField label="Candidate" htmlFor="candidate" required>
          <Select id="candidate" value={candidateId} onChange={(e) => setCandidateId(e.target.value)} aria-busy={isFetching}>
            <option value="">
              {page && page.total === 0 ? "No candidates match your search" : "Select a candidate…"}
            </option>
            {candidates?.map((c) => (
              <option key={c.id} value={c.id}>
                {c.full_name} — {c.professional_title || "No title"}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField label="Starting Stage" htmlFor="stage">
          <Select id="stage" value={stage} onChange={(e) => setStage(e.target.value)}>
            {CANONICAL_STAGES.map((s) => (
              <option key={s} value={s}>
                {stageLabel(s)}
              </option>
            ))}
          </Select>
        </FormField>
        {error && <p role="alert" className="text-sm text-dt-danger">{error}</p>}
        <div className="flex justify-end gap-3 pt-1">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" loading={mutation.isPending}>
            Add Candidate
          </Button>
        </div>
      </form>
    </Modal>
  );
}
