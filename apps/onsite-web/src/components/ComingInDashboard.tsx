import { EmptyState, PageHeader } from "@dijione/design-system";
import { Hourglass } from "lucide-react";

/** Placeholder for the Dashboard V1 (Phase 2) views. Navigation is in place;
 *  the attendance views ship once Phase 1 validation has passed. */
export function ComingInDashboard({ title, description }: { title: string; description: string }) {
  return (
    <div>
      <PageHeader title={title} description={description} />
      <EmptyState
        icon={Hourglass}
        title="Arriving with Dashboard V1"
        description="This view is part of the next phase. Attendance data is already being mirrored — see Site Health."
      />
    </div>
  );
}
