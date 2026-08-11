"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarClock, Plus, Video } from "lucide-react";
import { useState } from "react";
import { listInterviews, updateInterviewStatus } from "@/lib/api";
import { useTalentScope } from "@/lib/auth-context";
import type { ClientInterviewOut, InterviewOut } from "@/lib/types";
import { formatDateTime, stageLabel } from "@/lib/utils";
import { Button } from "@/components/ui/Button";
import { Select } from "@/components/ui/FormField";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/States";
import { Card } from "@/components/ui/Card";
import { INTERVIEW_STATUSES } from "@/lib/constants";
import { ScheduleInterviewModal } from "./ScheduleInterviewModal";

function isStaffInterview(i: InterviewOut | ClientInterviewOut): i is InterviewOut {
  return "client_name" in i;
}

export function InterviewList({ requestId }: { requestId?: number }) {
  const scope = useTalentScope();
  const queryClient = useQueryClient();
  const [scheduleOpen, setScheduleOpen] = useState(false);
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["interviews"],
    queryFn: listInterviews,
  });

  if (!scope) return null;
  if (isLoading) return <LoadingState label="Loading interviews…" />;
  if (isError) return <ErrorState onRetry={() => refetch()} />;

  const filtered = (data ?? []).filter((i) => (requestId ? i.talent_request_id === requestId : true));
  const sorted = [...filtered].sort(
    (a, b) => new Date(a.scheduled_at).getTime() - new Date(b.scheduled_at).getTime()
  );

  return (
    <div>
      {scope.isStaff && requestId && (
        <div className="mb-4 flex justify-end">
          <Button size="sm" onClick={() => setScheduleOpen(true)}>
            <Plus className="size-4" />
            Schedule Interview
          </Button>
        </div>
      )}

      {sorted.length === 0 ? (
        <EmptyState
          icon={CalendarClock}
          title="No interviews scheduled"
          description={
            scope.isStaff
              ? "Schedule an interview once a candidate has been shortlisted."
              : "Upcoming interviews will appear here."
          }
        />
      ) : (
        <div className="grid gap-3">
          {sorted.map((interview) => (
            <Card key={interview.id} className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between">
              <div className="flex items-start gap-3">
                <div className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-dt-surface-warm text-dt-burnt-orange">
                  <CalendarClock className="size-4.5" />
                </div>
                <div>
                  <p className="text-sm font-semibold text-dt-text-primary">
                    {interview.candidate_name} · {interview.designation}
                  </p>
                  <p className="text-xs text-dt-text-secondary">
                    {formatDateTime(interview.scheduled_at)} · {stageLabel(interview.interview_type)}
                    {isStaffInterview(interview) && interview.client_name ? ` · ${interview.client_name}` : ""}
                  </p>
                  {interview.meeting_link && (
                    <a
                      href={interview.meeting_link}
                      target="_blank"
                      rel="noreferrer"
                      className="mt-1 inline-flex items-center gap-1 text-xs font-medium text-dt-burnt-orange"
                    >
                      <Video className="size-3.5" />
                      Join meeting
                    </a>
                  )}
                </div>
              </div>

              <div className="flex items-center gap-2">
                {scope.isStaff ? (
                  <Select
                    value={interview.status}
                    onChange={async (e) => {
                      await updateInterviewStatus(interview.id, e.target.value);
                      queryClient.invalidateQueries({ queryKey: ["interviews"] });
                    }}
                    className="w-40 py-1.5 text-xs"
                  >
                    {INTERVIEW_STATUSES.map((s) => (
                      <option key={s} value={s}>
                        {stageLabel(s)}
                      </option>
                    ))}
                  </Select>
                ) : (
                  <StatusBadge status={interview.status} />
                )}
              </div>
            </Card>
          ))}
        </div>
      )}

      {scope.isStaff && requestId && (
        <ScheduleInterviewModal requestId={requestId} open={scheduleOpen} onClose={() => setScheduleOpen(false)} />
      )}
    </div>
  );
}
