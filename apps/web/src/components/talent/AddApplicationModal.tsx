"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { ApiError, createApplication, listCandidates } from "@/lib/api";
import { Modal } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";
import { FormField, Select } from "@/components/ui/FormField";
import { CANONICAL_STAGES } from "@/lib/constants";
import { stageLabel } from "@/lib/utils";

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
  const { data: candidates } = useQuery({
    queryKey: ["candidates", ""],
    queryFn: () => listCandidates(),
    enabled: open,
  });
  const [candidateId, setCandidateId] = useState<string>("");
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
        <FormField label="Candidate" htmlFor="candidate" required>
          <Select id="candidate" value={candidateId} onChange={(e) => setCandidateId(e.target.value)}>
            <option value="">Select from the candidate pool…</option>
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
        {error && <p className="text-sm text-dt-danger">{error}</p>}
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
