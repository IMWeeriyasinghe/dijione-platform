import type { TalentRequestOut } from "@dijione/contracts";
import { Card, CardContent } from "@dijione/design-system";
import { StageTimeline } from "@dijione/design-system";
import { formatDate } from "@dijione/design-system";

export function OverviewTab({ request }: { request: TalentRequestOut }) {
  return (
    <div className="grid gap-6 lg:grid-cols-3">
      <Card className="lg:col-span-2">
        <CardContent className="pt-5">
          <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-dt-text-secondary">
            Description
          </h3>
          <p className="whitespace-pre-line text-sm text-dt-text-primary">{request.description}</p>

          {request.required_skills.length > 0 && (
            <div className="mt-5">
              <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-dt-text-secondary">
                Required Skills
              </h3>
              <div className="flex flex-wrap gap-2">
                {request.required_skills.map((s) => (
                  <span
                    key={s}
                    className="rounded-full bg-dt-surface-warm px-2.5 py-1 text-xs font-medium text-dt-text-primary"
                  >
                    {s}
                  </span>
                ))}
              </div>
            </div>
          )}

          <dl className="mt-6 grid grid-cols-2 gap-4 text-sm sm:grid-cols-3">
            <div>
              <dt className="text-dt-text-secondary">Seniority</dt>
              <dd className="font-medium text-dt-text-primary">{request.seniority || "—"}</dd>
            </div>
            <div>
              <dt className="text-dt-text-secondary">Location</dt>
              <dd className="font-medium text-dt-text-primary">{request.location || "—"}</dd>
            </div>
            <div>
              <dt className="text-dt-text-secondary">Engagement</dt>
              <dd className="font-medium text-dt-text-primary">{request.engagement_type.replace("_", " ")}</dd>
            </div>
            <div>
              <dt className="text-dt-text-secondary">Target Start</dt>
              <dd className="font-medium text-dt-text-primary">
                {request.target_start_date ? formatDate(request.target_start_date) : "—"}
              </dd>
            </div>
            <div>
              <dt className="text-dt-text-secondary">Priority</dt>
              <dd className="font-medium text-dt-text-primary">{request.priority}</dd>
            </div>
          </dl>

          {request.notes && (
            <div className="mt-5">
              <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-dt-text-secondary">
                Notes
              </h3>
              <p className="whitespace-pre-line text-sm text-dt-text-primary">{request.notes}</p>
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardContent className="pt-5">
          <h3 className="mb-4 text-sm font-semibold uppercase tracking-wide text-dt-text-secondary">
            Progress
          </h3>
          <StageTimeline stages={request.stage_timeline} />
        </CardContent>
      </Card>
    </div>
  );
}
