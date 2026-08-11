"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, ClipboardCheck, Workflow } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { getTalentRequest } from "@/lib/api";
import { useTalentScope } from "@/lib/auth-context";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/Button";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { ErrorState, LoadingState } from "@/components/ui/States";
import { StageProgressBar } from "@/components/ui/Timeline";
import { OverviewTab } from "@/components/talent/tabs/OverviewTab";
import { ClientCandidatesTab, StaffCandidatesTab } from "@/components/talent/tabs/CandidatesTab";
import { MessagesTab } from "@/components/talent/tabs/MessagesTab";
import { DocumentsTab } from "@/components/talent/tabs/DocumentsTab";
import { InterviewList } from "@/components/talent/InterviewList";
import { ReviewRequestModal } from "@/components/talent/ReviewRequestModal";
import { UpdateStageModal } from "@/components/talent/UpdateStageModal";

const TABS = ["Overview", "Candidates", "Interviews", "Messages", "Documents"] as const;
type Tab = (typeof TABS)[number];

export function RequestDetail({ requestId, initialTab }: { requestId: number; initialTab?: Tab }) {
  const scope = useTalentScope();
  const [tab, setTab] = useState<Tab>(initialTab && TABS.includes(initialTab) ? initialTab : "Overview");
  const [reviewOpen, setReviewOpen] = useState(false);
  const [stageOpen, setStageOpen] = useState(false);

  const { data: request, isLoading, isError, refetch } = useQuery({
    queryKey: ["talent-request", requestId],
    queryFn: () => getTalentRequest(requestId),
  });

  if (!scope) return null;
  if (isLoading) return <LoadingState label="Loading request…" />;
  if (isError || !request) return <ErrorState onRetry={() => refetch()} />;

  const needsReview =
    scope.isCustomerSuccessOrManager &&
    (request.customer_success_status === "PENDING_REVIEW" ||
      request.customer_success_status === "CLARIFICATION_REQUIRED");

  return (
    <div>
      <Link
        href="/talent-flow/requests"
        className="mb-4 inline-flex items-center gap-1.5 text-sm text-dt-text-secondary hover:text-dt-text-primary"
      >
        <ArrowLeft className="size-4" />
        Back to requests
      </Link>

      <div className="mb-6 flex flex-col gap-4 rounded-2xl border border-dt-border bg-dt-surface p-5 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-xl font-semibold text-dt-text-primary">{request.designation}</h1>
            <StatusBadge status={request.lifecycle_status} />
          </div>
          <p className="mt-1 text-sm text-dt-text-secondary">
            {request.request_code}
            {scope.isStaff && request.client_name ? ` · ${request.client_name}` : ""}
          </p>
          <p className="mt-2 text-sm text-dt-text-primary">{request.client_safe_status_text}</p>
          <div className="mt-3 max-w-sm">
            <StageProgressBar percent={request.progress_percent} />
          </div>
        </div>

        {scope.isStaff && (
          <div className="flex shrink-0 flex-col gap-2 sm:items-end">
            {needsReview && (
              <Button size="sm" onClick={() => setReviewOpen(true)}>
                <ClipboardCheck className="size-4" />
                Review Request
              </Button>
            )}
            <Button size="sm" variant="secondary" onClick={() => setStageOpen(true)}>
              <Workflow className="size-4" />
              Update Stage
            </Button>
            <div className="flex items-center gap-2 text-xs text-dt-text-secondary">
              <span>CS: </span>
              <StatusBadge status={request.customer_success_status} />
              <span>TA: </span>
              <StatusBadge status={request.ta_status} />
            </div>
          </div>
        )}
      </div>

      <div className="mb-6 flex gap-1 overflow-x-auto border-b border-dt-border">
        {TABS.map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={cn(
              "whitespace-nowrap border-b-2 px-4 py-2.5 text-sm font-medium transition",
              tab === t
                ? "border-dt-orange text-dt-burnt-orange"
                : "border-transparent text-dt-text-secondary hover:text-dt-text-primary"
            )}
          >
            {t}
          </button>
        ))}
      </div>

      {tab === "Overview" && <OverviewTab request={request} />}
      {tab === "Candidates" &&
        (scope.isStaff ? <StaffCandidatesTab requestId={requestId} /> : <ClientCandidatesTab requestId={requestId} />)}
      {tab === "Interviews" && <InterviewList requestId={requestId} />}
      {tab === "Messages" && <MessagesTab requestId={requestId} />}
      {tab === "Documents" && <DocumentsTab requestId={requestId} />}

      <ReviewRequestModal requestId={requestId} open={reviewOpen} onClose={() => setReviewOpen(false)} />
      <UpdateStageModal
        requestId={requestId}
        currentStage={request.current_stage}
        open={stageOpen}
        onClose={() => setStageOpen(false)}
      />
    </div>
  );
}
