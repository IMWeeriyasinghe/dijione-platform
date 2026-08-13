"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { ApiError, createInterview, listApplications } from "@/lib/api";
import { Modal } from "@dijione/design-system";
import { Button } from "@dijione/design-system";
import { FormField, Input, Select } from "@dijione/design-system";
import { INTERVIEW_TYPES } from "@dijione/contracts";

export function ScheduleInterviewModal({
  requestId,
  open,
  onClose,
}: {
  requestId: number;
  open: boolean;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const { data: applications } = useQuery({
    queryKey: ["applications", requestId],
    queryFn: () => listApplications({ talent_request_id: requestId }),
    enabled: open,
  });

  const [applicationId, setApplicationId] = useState("");
  const [scheduledAt, setScheduledAt] = useState("");
  const [interviewType, setInterviewType] = useState<(typeof INTERVIEW_TYPES)[number]>("CLIENT_INTERVIEW");
  const [meetingLink, setMeetingLink] = useState("");
  const [clientVisible, setClientVisible] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: () =>
      createInterview({
        application_id: Number(applicationId),
        scheduled_at: new Date(scheduledAt).toISOString(),
        interview_type: interviewType,
        meeting_link: meetingLink,
        client_visible: clientVisible,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["interviews"] });
      setApplicationId("");
      setScheduledAt("");
      setMeetingLink("");
      onClose();
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Could not schedule the interview."),
  });

  return (
    <Modal open={open} onClose={onClose} title="Schedule Interview">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          setError(null);
          if (!applicationId || !scheduledAt) {
            setError("Select a candidate and a date/time.");
            return;
          }
          mutation.mutate();
        }}
        className="flex flex-col gap-4"
      >
        <FormField label="Candidate" htmlFor="application" required>
          <Select id="application" value={applicationId} onChange={(e) => setApplicationId(e.target.value)}>
            <option value="">Select a linked candidate…</option>
            {applications?.map((a) => (
              <option key={a.id} value={a.id}>
                {a.candidate_name}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField label="Date &amp; Time" htmlFor="scheduled-at" required>
          <Input
            id="scheduled-at"
            type="datetime-local"
            value={scheduledAt}
            onChange={(e) => setScheduledAt(e.target.value)}
            required
          />
        </FormField>
        <FormField label="Interview Type" htmlFor="interview-type">
          <Select
            id="interview-type"
            value={interviewType}
            onChange={(e) => setInterviewType(e.target.value as (typeof INTERVIEW_TYPES)[number])}
          >
            {INTERVIEW_TYPES.map((t) => (
              <option key={t} value={t}>
                {t.replace("_", " ")}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField label="Meeting Link" htmlFor="meeting-link">
          <Input
            id="meeting-link"
            value={meetingLink}
            onChange={(e) => setMeetingLink(e.target.value)}
            placeholder="https://…"
          />
        </FormField>
        <label className="flex items-center gap-2 text-sm text-dt-text-primary">
          <input
            type="checkbox"
            checked={clientVisible}
            onChange={(e) => setClientVisible(e.target.checked)}
            className="size-4 accent-[var(--dt-orange)]"
          />
          Visible to client
        </label>
        {error && <p className="text-sm text-dt-danger">{error}</p>}
        <div className="flex justify-end gap-3 pt-1">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" loading={mutation.isPending}>
            Schedule
          </Button>
        </div>
      </form>
    </Modal>
  );
}
