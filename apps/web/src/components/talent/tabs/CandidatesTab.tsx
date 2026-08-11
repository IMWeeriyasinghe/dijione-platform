"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, UserRound } from "lucide-react";
import { useState } from "react";
import {
  listApplications,
  listRequestCandidates,
  updateApplicationScore,
  updateApplicationStage,
  updateApplicationStatus,
  updateApplicationVisibility,
} from "@/lib/api";
import { CANONICAL_STAGES, APPLICATION_STATUSES } from "@/lib/constants";
import { stageLabel } from "@/lib/utils";
import { Button } from "@/components/ui/Button";
import { Select } from "@/components/ui/FormField";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/States";
import { Card } from "@/components/ui/Card";
import { Table, Thead, Th, Tr, Td } from "@/components/ui/Table";
import { AddApplicationModal } from "@/components/talent/AddApplicationModal";

export function StaffCandidatesTab({ requestId }: { requestId: number }) {
  const queryClient = useQueryClient();
  const [addOpen, setAddOpen] = useState(false);
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["applications", requestId],
    queryFn: () => listApplications({ talent_request_id: requestId }),
  });

  function invalidate() {
    queryClient.invalidateQueries({ queryKey: ["applications", requestId] });
    queryClient.invalidateQueries({ queryKey: ["talent-request", requestId] });
  }

  if (isLoading) return <LoadingState label="Loading candidates…" />;
  if (isError) return <ErrorState onRetry={() => refetch()} />;

  return (
    <div>
      <div className="mb-4 flex justify-end">
        <Button size="sm" onClick={() => setAddOpen(true)}>
          <Plus className="size-4" />
          Add Candidate
        </Button>
      </div>

      {!data || data.length === 0 ? (
        <EmptyState
          icon={UserRound}
          title="No candidates linked yet"
          description="Add a candidate from the pool to start tracking their application against this request."
          action={
            <Button size="sm" onClick={() => setAddOpen(true)}>
              Add Candidate
            </Button>
          }
        />
      ) : (
        <Table>
          <Thead>
            <tr>
              <Th>Candidate</Th>
              <Th>Stage</Th>
              <Th>Status</Th>
              <Th>Score</Th>
              <Th>Client Visible</Th>
            </tr>
          </Thead>
          <tbody>
            {data.map((app) => (
              <Tr key={app.id}>
                <Td className="font-medium">{app.candidate_name}</Td>
                <Td>
                  <Select
                    value={app.current_stage}
                    onChange={async (e) => {
                      await updateApplicationStage(app.id, e.target.value);
                      invalidate();
                    }}
                    className="w-44 py-1.5 text-xs"
                  >
                    {CANONICAL_STAGES.map((s) => (
                      <option key={s} value={s}>
                        {stageLabel(s)}
                      </option>
                    ))}
                  </Select>
                </Td>
                <Td>
                  <Select
                    value={app.status}
                    onChange={async (e) => {
                      await updateApplicationStatus(app.id, e.target.value);
                      invalidate();
                    }}
                    className="w-36 py-1.5 text-xs"
                  >
                    {APPLICATION_STATUSES.map((s) => (
                      <option key={s} value={s}>
                        {stageLabel(s)}
                      </option>
                    ))}
                  </Select>
                </Td>
                <Td>
                  <input
                    type="number"
                    min={0}
                    max={10}
                    step={0.1}
                    defaultValue={app.score ?? ""}
                    onBlur={async (e) => {
                      const value = e.target.value === "" ? null : Number(e.target.value);
                      if (value !== null) {
                        await updateApplicationScore(app.id, value);
                        invalidate();
                      }
                    }}
                    className="w-16 rounded-lg border border-dt-border px-2 py-1 text-xs focus:border-dt-orange focus:outline-none"
                  />
                </Td>
                <Td>
                  <label className="flex items-center gap-2 text-xs">
                    <input
                      type="checkbox"
                      defaultChecked={app.is_client_visible}
                      onChange={async (e) => {
                        await updateApplicationVisibility(app.id, e.target.checked);
                        invalidate();
                      }}
                      className="size-4 accent-[var(--dt-orange)]"
                    />
                    {app.is_client_visible ? <StatusBadge status="APPROVED" label="Visible" /> : "Hidden"}
                  </label>
                </Td>
              </Tr>
            ))}
          </tbody>
        </Table>
      )}

      <AddApplicationModal requestId={requestId} open={addOpen} onClose={() => setAddOpen(false)} />
    </div>
  );
}

export function ClientCandidatesTab({ requestId }: { requestId: number }) {
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["request-candidates", requestId],
    queryFn: () => listRequestCandidates(requestId),
  });

  if (isLoading) return <LoadingState label="Loading candidates…" />;
  if (isError) return <ErrorState onRetry={() => refetch()} />;
  if (!data || data.length === 0) {
    return (
      <EmptyState
        icon={UserRound}
        title="No candidates shared yet"
        description="Talent Acquisition will share candidates here as soon as they're ready for your review."
      />
    );
  }

  return (
    <div className="grid gap-4 sm:grid-cols-2">
      {data.map((c) => (
        <Card key={c.application_id} className="p-5">
          <p className="text-base font-semibold text-dt-text-primary">{c.full_name}</p>
          <p className="text-sm text-dt-text-secondary">{c.professional_title}</p>
          <div className="mt-3 flex flex-wrap gap-1.5">
            {c.skills.map((s) => (
              <span key={s} className="rounded-full bg-dt-surface-warm px-2 py-0.5 text-xs text-dt-text-primary">
                {s}
              </span>
            ))}
          </div>
          {c.relevant_experience_summary && (
            <p className="mt-3 text-sm text-dt-text-secondary">{c.relevant_experience_summary}</p>
          )}
          <div className="mt-4 flex items-center gap-2">
            <StatusBadge status={c.current_stage} />
            {c.upcoming_interview_status && <StatusBadge status={c.upcoming_interview_status} label="Interview scheduled" />}
          </div>
        </Card>
      ))}
    </div>
  );
}
