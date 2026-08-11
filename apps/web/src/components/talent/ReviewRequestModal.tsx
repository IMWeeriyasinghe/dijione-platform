"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { ApiError, reviewTalentRequest } from "@/lib/api";
import { Modal } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";
import { FormField, Select, Textarea } from "@/components/ui/FormField";

export function ReviewRequestModal({
  requestId,
  open,
  onClose,
}: {
  requestId: number;
  open: boolean;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [decision, setDecision] = useState("APPROVED");
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: () => reviewTalentRequest(requestId, decision, reason),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["talent-request", requestId] });
      queryClient.invalidateQueries({ queryKey: ["talent-requests"] });
      queryClient.invalidateQueries({ queryKey: ["ta-dashboard"] });
      setReason("");
      onClose();
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Could not submit the review."),
  });

  return (
    <Modal open={open} onClose={onClose} title="Customer Success Review">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          setError(null);
          mutation.mutate();
        }}
        className="flex flex-col gap-4"
      >
        <FormField label="Decision" htmlFor="decision">
          <Select id="decision" value={decision} onChange={(e) => setDecision(e.target.value)}>
            <option value="APPROVED">Approve — hand off to Talent Acquisition</option>
            <option value="CLARIFICATION_REQUIRED">Request clarification from client</option>
            <option value="REJECTED">Reject</option>
          </Select>
        </FormField>
        <FormField label="Notes" htmlFor="reason" hint="Visible to the client for rejections/clarifications.">
          <Textarea id="reason" value={reason} onChange={(e) => setReason(e.target.value)} />
        </FormField>
        {error && <p className="text-sm text-dt-danger">{error}</p>}
        <div className="flex justify-end gap-3 pt-1">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" loading={mutation.isPending}>
            Submit Decision
          </Button>
        </div>
      </form>
    </Modal>
  );
}
