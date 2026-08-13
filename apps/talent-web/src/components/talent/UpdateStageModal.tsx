"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { ApiError, updateTalentRequestStage } from "@/lib/api";
import { CANONICAL_STAGES } from "@dijione/contracts";
import { Modal } from "@dijione/design-system";
import { Button } from "@dijione/design-system";
import { FormField, Select, Textarea } from "@dijione/design-system";
import { stageLabel } from "@dijione/design-system";

export function UpdateStageModal({
  requestId,
  currentStage,
  open,
  onClose,
}: {
  requestId: number;
  currentStage: string;
  open: boolean;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [stage, setStage] = useState(currentStage);
  const [statusText, setStatusText] = useState("");
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: () => updateTalentRequestStage(requestId, stage, statusText || undefined),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["talent-request", requestId] });
      queryClient.invalidateQueries({ queryKey: ["talent-requests"] });
      setStatusText("");
      onClose();
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Could not update the stage."),
  });

  return (
    <Modal open={open} onClose={onClose} title="Update Recruitment Stage">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          setError(null);
          mutation.mutate();
        }}
        className="flex flex-col gap-4"
      >
        <FormField label="Stage" htmlFor="stage">
          <Select id="stage" value={stage} onChange={(e) => setStage(e.target.value)}>
            {CANONICAL_STAGES.map((s) => (
              <option key={s} value={s}>
                {stageLabel(s)}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField label="Client-Safe Status Text" htmlFor="status-text" hint="Shown to the client on their dashboard. Leave blank to use the default for this stage.">
          <Textarea
            id="status-text"
            value={statusText}
            onChange={(e) => setStatusText(e.target.value)}
            placeholder="e.g. Client interviews in progress"
          />
        </FormField>
        {error && <p className="text-sm text-dt-danger">{error}</p>}
        <div className="flex justify-end gap-3 pt-1">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" loading={mutation.isPending}>
            Update Stage
          </Button>
        </div>
      </form>
    </Modal>
  );
}
