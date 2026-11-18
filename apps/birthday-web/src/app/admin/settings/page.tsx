"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { ApiError, useBirthdayScope } from "@dijione/auth-client";
import {
  Button,
  EmptyState,
  ErrorState,
  FormField,
  Input,
  LoadingState,
  Modal,
  PageHeader,
} from "@dijione/design-system";
import { applyCleanStart, getCleanStartPreview, getConfig, updateConfig } from "@/lib/api";
import { addDaysIso, formatIsoDate, validateLeadTime, validateStartDate } from "@/lib/operational-settings";

// Operational settings (DIJI Birthday V1 go-live).
//
// first eligible birthday = Operational Start Date + Supplier Lead Time.
// Saving these settings never cancels anything. The pre-launch backlog is
// cleared only by the explicit, single-use "Apply clean start" action,
// after the admin has seen exactly what it will exclude. The backend
// enforces every rule here independently (birthday.config.manage, 422
// validation, 409 once applied or if the boundary changed since preview).

const STATUS_LABELS: Record<string, string> = {
  PENDING_VERIFICATION: "Pending verification",
  REQUIRES_REVIEW: "Requires review",
  REQUIRES_ATTENTION: "Requires attention",
  ON_HOLD: "On hold",
  SENT_TO_SUPPLIER: "Sent to supplier",
  CHANGE_REQUESTED: "Change requested",
  CONFIRMED: "Confirmed by supplier",
  PREPARING: "Preparing",
  OUT_FOR_DELIVERY: "Out for delivery",
};

function errorText(err: unknown): string {
  if (err instanceof ApiError) return err.message;
  return "Something went wrong. Please try again.";
}

export default function OperationalSettingsPage() {
  const scope = useBirthdayScope();
  const queryClient = useQueryClient();
  const isAdmin = !!scope?.isAdmin;

  const configQuery = useQuery({ queryKey: ["birthday-config"], queryFn: getConfig, enabled: isAdmin });
  const previewQuery = useQuery({
    queryKey: ["birthday-clean-start-preview"],
    queryFn: getCleanStartPreview,
    enabled: isAdmin,
  });

  // Drafts stay null until the admin edits a field; until then the inputs
  // show the saved values.
  const [startDraft, setStartDate] = useState<string | null>(null);
  const [leadDraft, setLeadTime] = useState<string | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const startDate = startDraft ?? configQuery.data?.operational_start_date ?? "";
  const leadTime = leadDraft ?? String(configQuery.data?.supplier_lead_time_days ?? 7);

  const startError = validateStartDate(startDate);
  const leadError = validateLeadTime(leadTime);
  const firstEligible = useMemo(
    () => (startDate && !startError && !leadError ? addDaysIso(startDate, Number(leadTime)) : null),
    [startDate, leadTime, startError, leadError],
  );

  const saved = configQuery.data;
  const dirty =
    !!saved &&
    ((saved.operational_start_date ?? "") !== startDate || String(saved.supplier_lead_time_days) !== leadTime);

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["birthday-config"] });
    queryClient.invalidateQueries({ queryKey: ["birthday-clean-start-preview"] });
  };

  const saveMutation = useMutation({
    mutationFn: () =>
      updateConfig({
        operational_start_date: startDate || null,
        supplier_lead_time_days: Number(leadTime),
      }),
    onSuccess: () => {
      setStartDate(null);
      setLeadTime(null);
      refresh();
    },
  });

  const applyMutation = useMutation({
    mutationFn: (boundary: string) => applyCleanStart(boundary),
    onSuccess: () => {
      setConfirmOpen(false);
      refresh();
    },
  });

  if (!isAdmin) {
    return (
      <EmptyState
        title="Admin access required"
        description="Operational settings are available to DijiBirthday administrators."
      />
    );
  }

  if (configQuery.isLoading || previewQuery.isLoading) return <LoadingState label="Loading operational settings…" />;
  if (configQuery.isError || !configQuery.data) return <ErrorState onRetry={() => configQuery.refetch()} />;

  const preview = previewQuery.data;
  const applied = !!saved?.clean_start_applied_at;
  const canApply =
    !applied && !dirty && !!saved?.first_eligible_birthday && !!preview && preview.first_eligible_birthday !== null;

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Operational Settings"
        description="When DijiBirthday starts processing birthdays, and the notice the supplier needs."
      />

      <section className="rounded-xl border border-dt-border bg-dt-surface p-5">
        <h2 className="text-base font-semibold text-dt-text-primary">Go-live boundary</h2>
        <div className="mt-4 grid gap-4 sm:grid-cols-2">
          <FormField
            label="Operational Start Date"
            htmlFor="operational-start-date"
            hint={startError ?? "The day DijiBirthday begins operational processing."}
          >
            <Input
              id="operational-start-date"
              type="date"
              value={startDate}
              aria-invalid={!!startError}
              onChange={(e) => setStartDate(e.target.value)}
            />
          </FormField>
          <FormField
            label="Supplier Lead Time (days)"
            htmlFor="supplier-lead-time"
            hint={leadError ?? "Minimum notice the supplier needs before a birthday."}
          >
            <Input
              id="supplier-lead-time"
              type="number"
              min={0}
              max={60}
              value={leadTime}
              aria-invalid={!!leadError}
              onChange={(e) => setLeadTime(e.target.value)}
            />
          </FormField>
        </div>

        <p className="mt-4 text-sm text-dt-text-primary" data-testid="first-eligible">
          {firstEligible ? (
            <>
              First eligible birthday: <strong>{firstEligible}</strong> ({formatIsoDate(firstEligible)})
            </>
          ) : (
            "Set an operational start date to see the first eligible birthday."
          )}
        </p>
        <p className="mt-1 text-xs text-dt-text-secondary">
          Only birthdays on or after this date are processed. An employee whose birthday falls earlier this year
          is processed normally next year. Per-supplier lead times still apply to each order as before.
        </p>

        {saveMutation.isError && <p className="mt-3 text-sm text-dt-danger">{errorText(saveMutation.error)}</p>}
        <div className="mt-4 flex justify-end">
          <Button
            size="sm"
            disabled={!dirty || !!startError || !!leadError}
            loading={saveMutation.isPending}
            onClick={() => saveMutation.mutate()}
          >
            Save settings
          </Button>
        </div>
      </section>

      <section className="rounded-xl border border-dt-border bg-dt-surface p-5">
        <h2 className="text-base font-semibold text-dt-text-primary">Clean start (one time)</h2>
        {applied ? (
          <p className="mt-3 text-sm text-dt-text-primary" data-testid="clean-start-applied">
            Clean start applied on {formatIsoDate(saved!.clean_start_applied_at!.slice(0, 10))}:{" "}
            {saved!.clean_start_excluded_count ?? 0} pre-launch orders were excluded (first eligible birthday{" "}
            {saved!.clean_start_first_eligible}). This action cannot be repeated.
          </p>
        ) : dirty ? (
          <p className="mt-3 text-sm text-dt-text-secondary">Save the settings above to preview the clean start.</p>
        ) : !preview || preview.first_eligible_birthday === null ? (
          <p className="mt-3 text-sm text-dt-text-secondary">
            Save an operational start date to preview which pre-launch orders would be excluded.
          </p>
        ) : (
          <div className="mt-3 flex flex-col gap-3 text-sm text-dt-text-primary" data-testid="clean-start-preview">
            <p>
              Establishing the operational baseline excludes every open order whose birthday is before{" "}
              <strong>{preview.first_eligible_birthday}</strong>.
            </p>
            <p>
              <strong>{preview.total}</strong> order{preview.total === 1 ? "" : "s"} will be excluded.
            </p>
            {preview.total > 0 && (
              <ul className="list-disc pl-5">
                {Object.entries(preview.by_status).map(([status, count]) => (
                  <li key={status}>
                    {STATUS_LABELS[status] ?? status}: {count}
                  </li>
                ))}
              </ul>
            )}
            {preview.released_to_supplier > 0 && (
              <p className="text-dt-warning" data-testid="released-warning">
                {preview.released_to_supplier} of these {preview.released_to_supplier === 1 ? "was" : "were"} already
                sent to the supplier and will show as cancelled in the Supplier Portal.
              </p>
            )}
            <p className="text-dt-text-secondary">
              No supplier cancellation email is sent. Nothing is deleted: excluded orders keep their full history,
              are marked “Excluded — before operational start”, and can be reopened individually.
            </p>
            <div className="flex justify-end">
              <Button size="sm" disabled={!canApply} onClick={() => setConfirmOpen(true)}>
                Apply clean start…
              </Button>
            </div>
          </div>
        )}
      </section>

      <Modal open={confirmOpen} onClose={() => setConfirmOpen(false)} title="Establish the operational baseline">
        <div className="flex flex-col gap-4 text-sm text-dt-text-primary">
          <p>
            This sets the DijiBirthday operational baseline. First eligible birthday:{" "}
            <strong>{preview?.first_eligible_birthday}</strong>.
          </p>
          <p>
            <strong>{preview?.total ?? 0}</strong> pre-launch order{preview?.total === 1 ? "" : "s"} will be moved
            to Cancelled (excluded)
            {preview && preview.released_to_supplier > 0
              ? `, including ${preview.released_to_supplier} already sent to the supplier`
              : ""}
            . No supplier email is sent and history is retained.
          </p>
          <p>This can only be done once.</p>
          {applyMutation.isError && <p className="text-dt-danger">{errorText(applyMutation.error)}</p>}
          <div className="flex justify-end gap-2">
            <Button variant="secondary" size="sm" onClick={() => setConfirmOpen(false)}>
              Cancel
            </Button>
            <Button
              size="sm"
              loading={applyMutation.isPending}
              onClick={() => preview?.first_eligible_birthday && applyMutation.mutate(preview.first_eligible_birthday)}
            >
              Confirm clean start
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
