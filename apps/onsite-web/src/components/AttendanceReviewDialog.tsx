"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, Modal } from "@dijione/design-system";
import { ToneBadge } from "@/components/ToneBadge";
import { cx, Field, fieldClass, InlineAlert, SkeletonRows } from "@/components/kit";
import {
  DECLARATION_SOURCES, EXCEPTION_TYPES, getReviewDay, JUSTIFICATION_REASONS, openReview, OUTCOMES, reopenReview,
  resolveReview, submitReview,
  type DayFacts, type DeclarationSource, type ExceptionType, type JustificationReason, type Outcome, type ReviewDetail,
} from "@/lib/dashboard";
import { localTime } from "@/lib/flags";
import { FINGERPRINT_DISCLAIMER, formatRecordedSpan, RECORDED_SPAN_HELP, SEQUENCE_LABEL } from "@/lib/format";
import { fmtDay } from "@/lib/period";
import {
  MIN_TEXT, OUTCOME_LABEL, REASON_LABEL, REASSESS_LABEL, reviewError, SOURCE_LABEL, STATUS_LABEL, STATUS_TONE,
  TYPE_LABEL,
} from "@/lib/reviews";

export type ReviewTarget = {
  siteId: string;
  date: string;
  /** A verified team member (PERSON case) … */
  bamboohrId?: string | null;
  /** … or a raw unmapped / conflict ZKBioTime ID (CODE case). */
  zkEmpCode?: string | null;
  label: string;
  single?: boolean;
};

function Select<T extends string>({ label, value, options, onChange }: {
  label: string; value: T | ""; options: readonly { value: T | ""; label: string }[]; onChange: (v: T | "") => void;
}) {
  return (
    <Field label={label}>
      <select aria-label={label} className={fieldClass} value={value} onChange={(e) => onChange(e.target.value as T | "")}>
        {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
    </Field>
  );
}

function Text({ label, value, onChange, rows, placeholder }: {
  label: string; value: string; onChange: (v: string) => void; rows?: number; placeholder?: string;
}) {
  return (
    <Field label={label}>
      {rows ? (
        <textarea aria-label={label} rows={rows} className={cx(fieldClass, "h-auto py-2")} value={value}
          placeholder={placeholder} onChange={(e) => onChange(e.target.value)} />
      ) : (
        <input aria-label={label} className={fieldClass} value={value} placeholder={placeholder}
          onChange={(e) => onChange(e.target.value)} />
      )}
    </Field>
  );
}

function FactsBlock({ facts, title }: { facts: DayFacts; title: string }) {
  return (
    <div className="rounded-lg border border-dt-border bg-dt-surface-warm/40 p-3 text-sm">
      <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-dt-text-secondary">{title}</p>
      <dl className="grid grid-cols-2 gap-x-4 gap-y-1 sm:grid-cols-4">
        <div><dt className="text-xs text-dt-text-secondary">First recorded fingerprint</dt><dd>{localTime(facts.first_local)}</dd></div>
        <div><dt className="text-xs text-dt-text-secondary">Last recorded fingerprint</dt><dd>{localTime(facts.last_local)}</dd></div>
        <div><dt className="text-xs text-dt-text-secondary" title={RECORDED_SPAN_HELP}>Recorded Span</dt>
          <dd>{facts.recorded_span_minutes === null ? "—, Single Recorded Fingerprint" : formatRecordedSpan(facts.recorded_span_minutes)}</dd></div>
        <div><dt className="text-xs text-dt-text-secondary">Punches</dt><dd className="tabular-nums">{facts.punch_count}</dd></div>
      </dl>
    </div>
  );
}

/** Estimate preview (client-side, labelled as an estimate — the server computes the stored value). */
function previewEstimate(first: string | null, declared: string): string | null {
  const f = /T(\d{2}):(\d{2})/.exec(first ?? "");
  const d = /^(\d{1,2}):(\d{2})$/.exec(declared.trim());
  if (!f || !d) return null;
  const minutes = Number(d[1]) * 60 + Number(d[2]) - (Number(f[1]) * 60 + Number(f[2]));
  return minutes > 0 ? formatRecordedSpan(minutes) : null;
}

/** View or act on the attendance review case of one identity-day. On-site Users
 *  see it read-only; only On-site Admins (server-enforced) open, justify,
 *  resolve or reopen. Fingerprint records are never changed. */
export function AttendanceReviewDialog({ target, onClose }: { target: ReviewTarget; onClose: () => void }) {
  const qc = useQueryClient();
  const params = { site_id: target.siteId, date: target.date,
    ...(target.bamboohrId ? { bamboohr_id: target.bamboohrId } : { zk_emp_code: target.zkEmpCode ?? "" }) };
  const key = ["onsite-review-day", params];
  const day = useQuery({ queryKey: key, queryFn: () => getReviewDay(params) });
  const [error, setError] = useState<string | null>(null);
  const [type, setType] = useState<ExceptionType | "">(target.single ? "SINGLE_RECORDED_FINGERPRINT" : "");
  const [reason, setReason] = useState<JustificationReason | "">("");
  const [explanation, setExplanation] = useState("");
  const [declared, setDeclared] = useState("");
  const [source, setSource] = useState<DeclarationSource | "">("");
  const [evidence, setEvidence] = useState("");
  const [outcome, setOutcome] = useState<Outcome | "">("");
  const [note, setNote] = useState("");

  const done = (d: ReviewDetail) => {
    qc.setQueryData(key, d);
    qc.invalidateQueries({ predicate: (q) => String(q.queryKey[0]).startsWith("onsite-") && q.queryKey[0] !== "onsite-review-day" });
    setError(null);
  };
  const act = useMutation({ mutationFn: (fn: () => Promise<ReviewDetail>) => fn(), onSuccess: done,
    onError: (e) => { setError(reviewError(e)); qc.invalidateQueries({ queryKey: key }); } });

  const d = day.data;
  const c = d?.case ?? null;
  const manage = Boolean(d?.can_manage);
  const allowed = new Set(c?.allowed_actions ?? []);
  const facts = d?.current_facts;

  return (
    <Modal open onClose={onClose} title={`Attendance review — ${target.label}, ${fmtDay(target.date, true)}`}>
      <div className="max-h-[75vh] space-y-4 overflow-y-auto pr-1">
        <p className="text-xs text-dt-text-secondary">{FINGERPRINT_DISCLAIMER} A review is an administrative record: it never changes fingerprint records or identity mappings, and a resolved case is not a verified duration.</p>
        {day.isLoading || !d ? <SkeletonRows rows={3} label="Loading review…" /> : (
          <>
            {facts && <FactsBlock facts={facts} title="Recorded evidence (current)" />}
            <ol className="flex flex-wrap gap-2 text-xs" aria-label="Recorded fingerprints of the day">
              {d.punches.map((p) => (
                <li key={`${p.position}-${p.local_time}`} className="rounded-full border border-dt-border px-2 py-0.5">
                  <span className="font-medium tabular-nums">{localTime(p.local_time)}</span>{" "}
                  <span className="text-dt-text-secondary">{SEQUENCE_LABEL[p.sequence]} · {p.position} of {p.of}{p.terminal ? ` · ${p.terminal}` : ""}</span>
                </li>
              ))}
            </ol>

            {c ? (
              <div className="space-y-3">
                <div className="flex flex-wrap items-center gap-2">
                  <ToneBadge tone={STATUS_TONE[c.status]}>{STATUS_LABEL[c.status]}</ToneBadge>
                  <ToneBadge tone="neutral">{TYPE_LABEL[c.exception_type]}</ToneBadge>
                  {c.stale && <ToneBadge tone="warning">Needs reassessment</ToneBadge>}
                  <span className="text-xs text-dt-text-secondary">Case #{c.id} · version {c.version}</span>
                </div>
                {c.stale && (
                  <InlineAlert tone="warning">
                    {(c.reassess_reasons ?? []).map((r) => REASSESS_LABEL[r]).join("; ")}. Nothing was changed automatically — compare the facts below and resubmit or reopen.
                  </InlineAlert>
                )}
                {c.stale && <FactsBlock facts={c.facts_snapshot} title="Recorded evidence when last reviewed" />}
                <dl className="grid grid-cols-1 gap-2 text-sm sm:grid-cols-2">
                  {c.justification_reason && <div><dt className="text-xs text-dt-text-secondary">Justification</dt><dd>{REASON_LABEL[c.justification_reason]}</dd></div>}
                  {c.explanation && <div className="sm:col-span-2"><dt className="text-xs text-dt-text-secondary">Explanation</dt><dd className="whitespace-pre-wrap">{c.explanation}</dd></div>}
                  {c.declared_departure_local && <div><dt className="text-xs text-dt-text-secondary">Declared departure (administrative declaration)</dt>
                    <dd>{localTime(c.declared_departure_local)} · {c.declaration_source ? SOURCE_LABEL[c.declaration_source] : ""}</dd></div>}
                  {c.estimated_minutes !== null && <div><dt className="text-xs text-dt-text-secondary">Estimated interval — reviewed declaration, not a confirmed duration</dt>
                    <dd>{formatRecordedSpan(c.estimated_minutes)}</dd></div>}
                  {c.estimate_basis && <div className="sm:col-span-2"><dt className="text-xs text-dt-text-secondary">Estimate basis</dt><dd>{c.estimate_basis}</dd></div>}
                  {c.outcome && <div><dt className="text-xs text-dt-text-secondary">Outcome</dt><dd>{OUTCOME_LABEL[c.outcome]} · Duration not verified</dd></div>}
                  {c.decision_note && <div className="sm:col-span-2"><dt className="text-xs text-dt-text-secondary">Decision note</dt><dd className="whitespace-pre-wrap">{c.decision_note}</dd></div>}
                  {c.reopen_reason && <div className="sm:col-span-2"><dt className="text-xs text-dt-text-secondary">Reopen reason</dt><dd>{c.reopen_reason}</dd></div>}
                </dl>
                <details className="text-sm">
                  <summary className="cursor-pointer text-dt-burnt-orange">History ({d.history.length})</summary>
                  <ol className="mt-2 space-y-1 text-xs text-dt-text-secondary">
                    {d.history.map((h) => (
                      <li key={`${h.version}-${h.at}`}>{new Date(h.at).toLocaleString()} — {h.action.toLowerCase()} by {h.actor_name ?? "an administrator"}
                        {" "}({h.from_status ? `${STATUS_LABEL[h.from_status]} → ` : ""}{STATUS_LABEL[h.to_status]}){h.note ? `: ${h.note}` : ""}</li>
                    ))}
                  </ol>
                </details>
              </div>
            ) : (
              <p className="text-sm text-dt-text-secondary">No review case for this day.{target.single ? " A Single Recorded Fingerprint is an observation; reviewing it is optional." : ""}</p>
            )}

            {error && <InlineAlert tone="danger">{error}</InlineAlert>}

            {!manage ? (
              c ? <p className="text-xs text-dt-text-secondary">Read-only: only an On-site Admin can change attendance reviews.</p> : null
            ) : !c ? (
              <div className="space-y-3 rounded-lg border border-dt-border p-3">
                <Select label="Classification" value={type} onChange={setType}
                  options={[{ value: "", label: "Choose…" }, ...EXCEPTION_TYPES.map((t) => ({ value: t, label: TYPE_LABEL[t] }))]} />
                <Button disabled={!type || act.isPending} onClick={() => act.mutate(() => openReview({
                  site_id: target.siteId, local_date: target.date, exception_type: type as ExceptionType,
                  ...(target.bamboohrId ? { bamboohr_id: target.bamboohrId } : { zk_emp_code: target.zkEmpCode ?? "" }),
                }))}>Open review case</Button>
              </div>
            ) : (
              <div className="space-y-4">
                {allowed.has("submit") && (
                  <form className="space-y-3 rounded-lg border border-dt-border p-3" onSubmit={(e) => {
                    e.preventDefault();
                    act.mutate(() => submitReview(c.id, { expected_version: c.version, justification_reason: reason as JustificationReason,
                      explanation, declared_departure_local: declared.trim() || null, declaration_source: (source || null) as DeclarationSource | null,
                      evidence_reference: evidence.trim() || null }));
                  }}>
                    <p className="text-sm font-semibold">{c.status === "SUBMITTED" ? "Update justification" : "Submit justification"}</p>
                    <Select label="Justification" value={reason} onChange={setReason}
                      options={[{ value: "", label: "Choose…" }, ...JUSTIFICATION_REASONS.map((r) => ({ value: r, label: REASON_LABEL[r] }))]} />
                    <Text label={`Explanation (at least ${MIN_TEXT} characters)`} value={explanation} onChange={setExplanation} rows={3} />
                    <div className="grid gap-3 sm:grid-cols-2">
                      <Text label="Declared departure (optional, site-local HH:MM, same date)" value={declared} onChange={setDeclared} placeholder="e.g. 17:30" />
                      <Select label="Declaration source" value={source} onChange={setSource}
                        options={[{ value: "", label: "None" }, ...DECLARATION_SOURCES.map((s) => ({ value: s, label: SOURCE_LABEL[s] }))]} />
                    </div>
                    {declared.trim() && (
                      <p className="text-xs text-dt-text-secondary">
                        Estimate preview (reviewed declaration, not a confirmed duration): {previewEstimate(facts?.first_local ?? null, declared) ?? "—"}.
                        It must not be earlier than the latest recorded fingerprint ({localTime(facts?.last_local)}); next-day declarations are not supported.
                      </p>
                    )}
                    <Text label="Evidence reference (optional)" value={evidence} onChange={setEvidence} />
                    <Button type="submit" disabled={!reason || explanation.trim().length < MIN_TEXT || (Boolean(declared.trim()) && !source) || act.isPending}>
                      {c.status === "SUBMITTED" ? "Save update" : "Submit justification"}
                    </Button>
                  </form>
                )}
                {allowed.has("resolve") && (
                  <form className="space-y-3 rounded-lg border border-dt-border p-3" onSubmit={(e) => {
                    e.preventDefault();
                    act.mutate(() => resolveReview(c.id, { expected_version: c.version, outcome: outcome as Outcome, decision_note: note }));
                  }}>
                    <p className="text-sm font-semibold">Resolve (administrative decision — duration not verified)</p>
                    <Select label="Outcome" value={outcome} onChange={setOutcome}
                      options={[{ value: "", label: "Choose…" }, ...OUTCOMES.map((o) => ({ value: o, label: OUTCOME_LABEL[o] }))]} />
                    <Text label={`Decision note (at least ${MIN_TEXT} characters)`} value={note} onChange={setNote} rows={2} />
                    <Button type="submit" disabled={!outcome || note.trim().length < MIN_TEXT || act.isPending}>Resolve case</Button>
                  </form>
                )}
                {allowed.has("reopen") && (
                  <form className="space-y-3 rounded-lg border border-dt-border p-3" onSubmit={(e) => {
                    e.preventDefault();
                    act.mutate(() => reopenReview(c.id, { expected_version: c.version, reason: note }));
                  }}>
                    <p className="text-sm font-semibold">Reopen</p>
                    <Text label={`Reason (at least ${MIN_TEXT} characters)`} value={note} onChange={setNote} rows={2} />
                    <Button type="submit" variant="secondary" disabled={note.trim().length < MIN_TEXT || act.isPending}>Reopen case</Button>
                  </form>
                )}
              </div>
            )}
          </>
        )}
      </div>
    </Modal>
  );
}
