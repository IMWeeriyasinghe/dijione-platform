import Link from "next/link";
import type { TalentRequestOut } from "@/lib/types";
import { Card } from "@/components/ui/Card";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { CompactStageStrip, StageProgressBar } from "@/components/ui/Timeline";

export function RequestCard({
  request,
  showClient = false,
}: {
  request: TalentRequestOut;
  showClient?: boolean;
}) {
  return (
    <Link href={`/talent-flow/requests/${request.id}`}>
      <Card className="flex h-full flex-col gap-3 p-5 transition hover:-translate-y-0.5 hover:shadow-md">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="truncate text-base font-semibold text-dt-text-primary">{request.designation}</p>
            <p className="text-xs text-dt-text-secondary">
              {request.request_code}
              {showClient && request.client_name ? ` · ${request.client_name}` : ""}
            </p>
          </div>
          <StatusBadge status={request.lifecycle_status} />
        </div>

        <CompactStageStrip stages={request.stage_timeline} />
        <StageProgressBar percent={request.progress_percent} />

        <p className="text-sm text-dt-text-secondary">{request.client_safe_status_text}</p>

        <div className="mt-auto flex items-center justify-between pt-1 text-xs text-dt-text-secondary">
          <span>{request.active_application_count} active candidate(s)</span>
          <StatusBadge status={request.current_stage} />
        </div>
      </Card>
    </Link>
  );
}
