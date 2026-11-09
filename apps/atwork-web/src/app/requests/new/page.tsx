"use client";

import { Suspense, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, Card, FormField, Input, LoadingState, PageHeader, Select, Textarea } from "@dijione/design-system";
import { Plus, Trash2 } from "lucide-react";
import { Notice, Page, QueryError, RequirePermission } from "@/components/ui";
import { attendance, corrections, errorMessage, isUncertain, newRequestId, type Session, type WorkMode } from "@/lib/api";
import { ALL_WORK_MODES, localInputToUtc, utcToLocalInput, WORK_MODE_LABEL } from "@/lib/format";
import { PERM } from "@/lib/atwork-scope";
import { usePolicy } from "@/lib/hooks";

type BreakRow = { key: number; start: string; end: string };
let nextKey = 0;

function validate(checkIn: string, checkOut: string, breaks: BreakRow[], isOpen: boolean, reason: string): string | null {
  if (!checkIn) return "Enter a check-in time.";
  if (!isOpen && !checkOut) return "Enter a check-out time.";
  if (checkOut && checkOut < checkIn) return "Check-out must not be before check-in.";
  for (const b of breaks) {
    if (!b.start || !b.end) return "Enter a start and end for each break.";
    if (b.end < b.start) return "A break must not end before it starts.";
    if (b.start < checkIn || (checkOut && b.end > checkOut)) return "Breaks must fall within the session.";
  }
  const sorted = [...breaks].sort((a, b) => a.start.localeCompare(b.start));
  for (let i = 1; i < sorted.length; i++) if (sorted[i].start < sorted[i - 1].end) return "Breaks must not overlap.";
  if (reason.trim().length < 5) return "Give a reason of at least 5 characters.";
  return null;
}

function Form({ session, zone, enabled }: { session: Session | null; zone: string; enabled: WorkMode[] }) {
  const router = useRouter();
  const client = useQueryClient();
  const toInput = (iso: string | null) => (iso ? utcToLocalInput(iso, zone) : "");
  const [mode, setMode] = useState<WorkMode>(session?.work_mode ?? enabled[0]);
  const [checkIn, setCheckIn] = useState(toInput(session?.check_in_at ?? null));
  const [checkOut, setCheckOut] = useState(toInput(session?.check_out_at ?? null));
  const [breaks, setBreaks] = useState<BreakRow[]>(session?.breaks.map((b) => ({ key: nextKey++, start: toInput(b.started_at), end: toInput(b.ended_at) })) ?? []);
  const [reason, setReason] = useState("");
  const [problem, setProblem] = useState<string | null>(null);
  // Kept across an uncertain failure; any edit makes it a different request.
  const requestId = useRef(newRequestId());
  const edited = <T,>(set: (v: T) => void) => (v: T) => { requestId.current = newRequestId(); set(v); };
  const isOpen = session?.status === "OPEN";

  const submit = useMutation({
    mutationFn: () => corrections.submit({
      client_request_id: requestId.current,
      session_id: session?.id,
      reason: reason.trim(),
      work_mode: mode,
      check_in_at: localInputToUtc(checkIn, zone),
      check_out_at: checkOut ? localInputToUtc(checkOut, zone) : undefined,
      breaks: breaks.map((b) => ({ started_at: localInputToUtc(b.start, zone), ended_at: localInputToUtc(b.end, zone) })),
    }),
    onSuccess: () => { client.invalidateQueries({ queryKey: ["atwork"] }); router.push("/requests"); },
    onError: (error) => { if (!isUncertain(error)) requestId.current = newRequestId(); },
  });

  const updateBreak = (key: number, patch: Partial<BreakRow>) => edited(setBreaks)(breaks.map((b) => (b.key === key ? { ...b, ...patch } : b)));
  const errorText = problem ?? (submit.isError ? (isUncertain(submit.error) ? "We could not confirm your request. Submit again safely: it will not be duplicated." : errorMessage(submit.error)) : null);

  return (
    <form noValidate onSubmit={(e) => {
      e.preventDefault();
      const invalid = validate(checkIn, checkOut, breaks, isOpen, reason);
      setProblem(invalid);
      if (!invalid && !submit.isPending) submit.mutate();
    }}>
      {errorText && <Notice tone="error">{errorText}</Notice>}
      <Card className="space-y-4 p-5">
        <p className="text-sm text-dt-text-secondary">Enter times in {zone}. Your official record does not change unless Management approves this request.</p>
        <FormField label="Work mode" htmlFor="mode" required><Select id="mode" value={mode} onChange={(e) => edited(setMode)(e.target.value as WorkMode)}>{ALL_WORK_MODES.filter((m) => enabled.includes(m) || m === session?.work_mode).map((m) => <option key={m} value={m}>{WORK_MODE_LABEL[m]}</option>)}</Select></FormField>
        <div className="grid gap-4 sm:grid-cols-2">
          <FormField label="Check-in" htmlFor="in" required><Input id="in" type="datetime-local" step={1} value={checkIn} onChange={(e) => edited(setCheckIn)(e.target.value)} /></FormField>
          <FormField label="Check-out" htmlFor="out" required={!isOpen} hint={isOpen ? "Enter this if you forgot to check out." : undefined}><Input id="out" type="datetime-local" step={1} value={checkOut} onChange={(e) => edited(setCheckOut)(e.target.value)} /></FormField>
        </div>
        <fieldset>
          <legend className="text-sm font-medium">Breaks</legend>
          <div className="mt-2 space-y-2">
            {breaks.map((b, i) => (
              <div key={b.key} className="flex flex-wrap items-end gap-2">
                <div className="min-w-48 flex-1"><FormField label={`Break ${i + 1} start`} htmlFor={`bs-${b.key}`}><Input id={`bs-${b.key}`} type="datetime-local" step={1} value={b.start} onChange={(e) => updateBreak(b.key, { start: e.target.value })} /></FormField></div>
                <div className="min-w-48 flex-1"><FormField label={`Break ${i + 1} end`} htmlFor={`be-${b.key}`}><Input id={`be-${b.key}`} type="datetime-local" step={1} value={b.end} onChange={(e) => updateBreak(b.key, { end: e.target.value })} /></FormField></div>
                <Button type="button" variant="ghost" aria-label={`Remove break ${i + 1}`} onClick={() => edited(setBreaks)(breaks.filter((x) => x.key !== b.key))}><Trash2 className="size-4" aria-hidden /></Button>
              </div>
            ))}
          </div>
          <Button type="button" variant="secondary" size="sm" className="mt-2" onClick={() => edited(setBreaks)([...breaks, { key: nextKey++, start: "", end: "" }])}><Plus className="size-4" aria-hidden />Add break</Button>
        </fieldset>
        <FormField label="Reason" htmlFor="reason" required><Textarea id="reason" value={reason} maxLength={1000} onChange={(e) => edited(setReason)(e.target.value)} /></FormField>
        <Button type="submit" loading={submit.isPending}>Submit request</Button>
      </Card>
    </form>
  );
}

function Screen() {
  const sessionId = useSearchParams().get("sessionId");
  const policy = usePolicy();
  const session = useQuery({ queryKey: ["atwork", "session", sessionId], queryFn: () => attendance.session(sessionId as string), enabled: Boolean(sessionId), retry: false });
  if (policy.isLoading || (sessionId && session.isLoading)) return <LoadingState />;
  if (!policy.data) return <QueryError error={policy.error} retry={() => policy.refetch()} />;
  if (sessionId && !session.data) return <QueryError error={session.error} retry={() => session.refetch()} />;
  return (
    <>
      <PageHeader title={sessionId ? "Request a correction" : "Request a missing session"} description="Management reviews every request." />
      <Form session={session.data ?? null} zone={policy.data.business_time_zone} enabled={policy.data.enabled_work_modes} />
    </>
  );
}

export default function NewRequestPage() {
  return <Page><RequirePermission permission={PERM.REQUEST_OWN} title="Correction access required"><Suspense fallback={<LoadingState />}><Screen /></Suspense></RequirePermission></Page>;
}
