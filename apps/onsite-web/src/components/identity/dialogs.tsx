"use client";

import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, Modal } from "@dijione/design-system";
import { ToneBadge } from "@/components/ToneBadge";
import { cx, Field, fieldClass, InlineAlert, SkeletonRows } from "@/components/kit";
import { ID_LABELS } from "@/lib/format";
import {
  closeMapping, correctMapping, createMapping, errorDetail, getCodeDetail, getEvidence, getMapping,
  reassignCode, rejectAssociation, searchDirectory, withdrawRejection, WARNING_LABEL,
  type DirectoryHit, type Mapping, type Rejection, type Warning,
} from "@/lib/identity";

export const MIN_TEXT = 10;

/** A complete, real calendar date (YYYY-MM-DD). Anything else blocks confirmation. */
export function isIsoDate(v: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(v)) return false;
  const d = new Date(`${v}T00:00:00Z`);
  return !Number.isNaN(d.getTime()) && d.toISOString().slice(0, 10) === v;
}

/* ------------------------------------------------------------------ shared */

function useInvalidate() {
  const qc = useQueryClient();
  // Mappings change attribution everywhere: refresh admin lists and dashboard views.
  return () => qc.invalidateQueries();
}

function ErrorBox({ error }: { error: unknown }) {
  if (!error) return null;
  const d = errorDetail(error);
  return (
    <InlineAlert tone="danger">
      {d.message ?? d.error ?? "The change was not saved."}
      {d.conflicts?.length ? <> Conflicting period(s): {d.conflicts.map((m) => `${m.zk_emp_code} → ${m.employee_name ?? m.bamboohr_id} (${m.valid_from} – ${m.valid_to ?? "open"})`).join("; ")}.</> : null}
      {d.rejections?.length ? <> A rejection covers this period.</> : null}
    </InlineAlert>
  );
}

export function TextField({ label, value, onChange, type = "text", required, placeholder, rows }: {
  label: string; value: string; onChange: (v: string) => void; type?: string; required?: boolean; placeholder?: string; rows?: number;
}) {
  return (
    <Field label={required ? `${label} (required)` : label}>
      {rows ? (
        <textarea aria-label={label} rows={rows} className={cx(fieldClass, "h-auto py-2")} value={value}
          placeholder={placeholder} onChange={(e) => onChange(e.target.value)} />
      ) : (
        <input aria-label={label} type={type} className={fieldClass} value={value} placeholder={placeholder}
          onChange={(e) => onChange(e.target.value)} />
      )}
    </Field>
  );
}

/** Directory search: results appear only for a typed query and NOTHING is
 *  pre-selected — not even when an Employee Number equals the ZKBioTime ID. */
export function EmployeePicker({ value, onChange }: { value: DirectoryHit | null; onChange: (h: DirectoryHit | null) => void }) {
  const [text, setText] = useState("");
  const [q, setQ] = useState("");
  useEffect(() => {
    const t = setTimeout(() => setQ(text.trim()), 300);
    return () => clearTimeout(t);
  }, [text]);
  const results = useQuery({ queryKey: ["onsite-identity-dir", q], queryFn: () => searchDirectory(q), enabled: q.length >= 2, retry: false });
  return (
    <div className="space-y-2">
      <TextField label="Search the BambooHR Workforce Directory" value={text} onChange={setText}
        placeholder="Name, BHR Employee ID or BambooHR Employee Number (2+ characters)" />
      {q.length >= 2 && results.isLoading && <SkeletonRows rows={2} label="Searching…" />}
      {results.isError && <ErrorBox error={results.error} />}
      {results.data && (
        results.data.items.length === 0 ? <p className="text-sm text-dt-text-secondary">No directory employee matches “{q}”.</p> : (
          <fieldset className="max-h-56 space-y-1 overflow-y-auto rounded-lg border border-dt-border p-2">
            <legend className="sr-only">Select the employee</legend>
            {results.data.items.map((h) => (
              <label key={h.bamboohr_id} className={cx("flex cursor-pointer items-start gap-2 rounded-md p-2 text-sm hover:bg-dt-surface-warm",
                value?.bamboohr_id === h.bamboohr_id && "bg-dt-cream")}>
                <input type="radio" name="employee" checked={value?.bamboohr_id === h.bamboohr_id} onChange={() => onChange(h)} className="mt-1" />
                <span className="min-w-0">
                  <span className="block font-medium text-dt-text-primary">{h.display_name ?? "—"}</span>
                  <span className="block text-xs text-dt-text-secondary">
                    {ID_LABELS.bhr} <span className="font-mono">{h.bamboohr_id}</span> · {ID_LABELS.number}{" "}
                    <span className="font-mono">{h.employee_number ?? "—"}</span> · {h.employment_status ?? "status unknown"}
                    {h.department ? ` · ${h.department}` : ""}
                  </span>
                  <span className="block text-xs text-dt-text-secondary">
                    Hired {h.hire_date ?? "—"}{h.termination_date ? ` · terminated ${h.termination_date}` : ""}
                    {h.active_codes.length ? ` · already mapped: ${h.active_codes.join(", ")}` : ""}
                  </span>
                </span>
              </label>
            ))}
          </fieldset>
        )
      )}
    </div>
  );
}

/** Every warning must be acknowledged individually before confirming. */
export function WarningChecklist({ warnings, acked, setAcked }: {
  warnings: Warning[]; acked: Set<string>; setAcked: (s: Set<string>) => void;
}) {
  if (!warnings.length) return <p className="text-sm text-dt-success">No evidence warnings for this period.</p>;
  return (
    <fieldset className="space-y-2 rounded-lg border border-dt-amber/50 bg-dt-amber/10 p-3">
      <legend className="px-1 text-sm font-medium text-dt-text-primary">Check each fact before confirming</legend>
      {warnings.map((w) => (
        <label key={w.code} className="flex items-start gap-2 text-sm">
          <input type="checkbox" className="mt-1" checked={acked.has(w.code)} onChange={(e) => {
            const next = new Set(acked);
            if (e.target.checked) next.add(w.code); else next.delete(w.code);
            setAcked(next);
          }} />
          <span><span className="font-medium">{WARNING_LABEL[w.code] ?? w.code}.</span> {w.message} <span className="text-dt-text-secondary">I have checked this.</span></span>
        </label>
      ))}
    </fieldset>
  );
}

function useWarnings(siteId: string, code: string, bid: string | undefined, from: string, to: string, excludeId?: number) {
  return useQuery({
    queryKey: ["onsite-identity-evidence", siteId, code, bid, from, to, excludeId],
    queryFn: () => getEvidence(code, { site_id: siteId, bamboohr_id: bid, proposed_from: from, proposed_to: to || undefined,
      exclude_mapping_id: excludeId }),
    enabled: Boolean(code && bid && isIsoDate(from) && (!to || isIsoDate(to))),
    retry: false,
  });
}

/** Warnings from the evidence preview, or the authoritative list the server returned on submit. */
function mergeWarnings(preview: Warning[] | undefined, fromServer: Warning[] | null): Warning[] {
  return fromServer ?? preview ?? [];
}

function Actions({ onCancel, confirm, disabled, busy }: { onCancel: () => void; confirm: string; disabled: boolean; busy: boolean }) {
  return (
    <div className="flex justify-end gap-2 pt-2">
      <Button variant="ghost" onClick={onCancel} type="button">Cancel</Button>
      <Button type="submit" disabled={disabled} loading={busy}>{confirm}</Button>
    </div>
  );
}

/* --------------------------------------------------------------- map (create) */

export function MapDialog({ siteId, code: initialCode, onClose }: { siteId: string; code?: string; onClose: () => void }) {
  const invalidate = useInvalidate();
  const [code, setCode] = useState(initialCode ?? "");
  const [emp, setEmp] = useState<DirectoryHit | null>(null);
  const [from, setFrom] = useState(""); // never defaulted: the administrator enters ownership start from evidence
  const [to, setTo] = useState("");
  const [evidence, setEvidence] = useState("");
  const [acked, setAcked] = useState<Set<string>>(new Set());
  const [serverWarnings, setServerWarnings] = useState<Warning[] | null>(null);
  const preview = useWarnings(siteId, code, emp?.bamboohr_id, from, to);
  const warnings = mergeWarnings(preview.data?.warnings, serverWarnings);
  const allAcked = warnings.every((w) => acked.has(w.code));
  const prior = warnings.find((w) => w.code === "PRIOR_UNMAPPED_ACTIVITY") as (Warning & { events?: number }) | undefined;
  const datesOk = isIsoDate(from) && (!to || isIsoDate(to));
  // Fail closed: confirm only after the evidence check for exactly these inputs succeeded.
  const ready = Boolean(code.trim() && emp && datesOk && evidence.trim().length >= MIN_TEXT && allAcked
    && preview.isSuccess && !preview.isFetching);
  const save = useMutation({
    mutationFn: () => createMapping({ site_id: siteId, zk_emp_code: code, bamboohr_id: emp!.bamboohr_id, valid_from: from,
      valid_to: to || null, evidence, acknowledged_warnings: [...acked] }),
    onSuccess: () => { invalidate(); onClose(); },
    onError: (e) => { const d = errorDetail(e); if (d.warnings) setServerWarnings(d.warnings); },
  });
  return (
    <Modal open onClose={onClose} title="Map ZKBioTime ID to a BambooHR employee">
      <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); if (ready) save.mutate(); }}>
        <TextField label={ID_LABELS.zk} value={code} onChange={setCode} required placeholder="Exact ZKBioTime ID" />
        <EmployeePicker value={emp} onChange={(h) => { setEmp(h); setAcked(new Set()); setServerWarnings(null); }} />
        <div className="grid grid-cols-2 gap-2">
          <TextField label="Owned from (site-local date)" type="date" value={from} onChange={(v) => { setFrom(v); setServerWarnings(null); }} required />
          <TextField label="Owned until (optional)" type="date" value={to} onChange={(v) => { setTo(v); setServerWarnings(null); }} />
        </div>
        <p className="text-xs text-dt-text-secondary">Enter the start date from HR or enrolment evidence. It is never assumed from the first recorded punch.</p>
        <TextField label="Verification evidence" rows={3} value={evidence} onChange={setEvidence} required
          placeholder="e.g. IT enrolment sheet 2026-11-01, confirmed by HR (min. 10 characters)" />
        {emp && from && !datesOk && <InlineAlert tone="danger">Enter complete dates (YYYY-MM-DD).</InlineAlert>}
        {emp && datesOk && (preview.isFetching ? <SkeletonRows rows={1} label="Checking evidence…" />
          : preview.isError ? <ErrorBox error={preview.error} />
          : preview.isSuccess ? <WarningChecklist warnings={warnings} acked={acked} setAcked={setAcked} /> : null)}
        {emp && datesOk && preview.isSuccess && (
          <p className="rounded-lg bg-dt-surface-warm p-2 text-sm" data-testid="confirm-sentence">
            Map {ID_LABELS.zk} <span className="font-mono">{code || "—"}</span> to {emp.display_name ?? "—"} ({ID_LABELS.bhr}{" "}
            <span className="font-mono">{emp.bamboohr_id}</span>, {ID_LABELS.number} <span className="font-mono">{emp.employee_number ?? "—"}</span>)
            {" "}from {from}{to ? ` until ${to}` : " (open-ended)"}
            {prior?.events ? ` — ${prior.events} earlier punch(es) stay unmapped.` : "."}
          </p>
        )}
        <ErrorBox error={save.error} />
        <Actions onCancel={onClose} confirm="Confirm mapping" disabled={!ready} busy={save.isPending} />
      </form>
    </Modal>
  );
}

/* ------------------------------------------------------------------ close */

export function CloseDialog({ mapping, onClose }: { mapping: Mapping; onClose: () => void }) {
  const invalidate = useInvalidate();
  const [to, setTo] = useState("");
  const [reason, setReason] = useState("");
  const save = useMutation({ mutationFn: () => closeMapping(mapping.id, { valid_to: to, reason }), onSuccess: () => { invalidate(); onClose(); } });
  return (
    <Modal open onClose={onClose} title={`End ownership of ${ID_LABELS.zk} ${mapping.zk_emp_code}`}>
      <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
        <p className="text-sm">{mapping.employee_name ?? mapping.bamboohr_id} owns this ID from {mapping.valid_from}. Attendance up to the end date stays attributed; later days become unmapped.</p>
        <TextField label="Last owned day (inclusive)" type="date" value={to} onChange={setTo} required />
        <TextField label="Reason" rows={2} value={reason} onChange={setReason} required />
        <ErrorBox error={save.error} />
        <Actions onCancel={onClose} confirm="End ownership" disabled={!isIsoDate(to) || reason.trim().length < MIN_TEXT} busy={save.isPending} />
      </form>
    </Modal>
  );
}

/* ---------------------------------------------------------------- correct */

export function CorrectDialog({ mapping, onClose }: { mapping: Mapping; onClose: () => void }) {
  const invalidate = useInvalidate();
  const [reason, setReason] = useState("");
  const [replace, setReplace] = useState(false);
  const [emp, setEmp] = useState<DirectoryHit | null>(null);
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [evidence, setEvidence] = useState("");
  const [acked, setAcked] = useState<Set<string>>(new Set());
  const [serverWarnings, setServerWarnings] = useState<Warning[] | null>(null);
  const preview = useWarnings(mapping.site_id, mapping.zk_emp_code, replace ? emp?.bamboohr_id : undefined, from, to, mapping.id);
  const warnings = mergeWarnings(preview.data?.warnings, serverWarnings);
  const replacementOk = !replace || Boolean(emp && isIsoDate(from) && (!to || isIsoDate(to)) && evidence.trim().length >= MIN_TEXT
    && preview.isSuccess && !preview.isFetching && warnings.every((w) => acked.has(w.code)));
  const save = useMutation({
    mutationFn: () => correctMapping(mapping.id, { reason, replacement: replace && emp ? {
      bamboohr_id: emp.bamboohr_id, valid_from: from, valid_to: to || null, evidence, acknowledged_warnings: [...acked] } : null }),
    onSuccess: () => { invalidate(); onClose(); },
    onError: (e) => { const d = errorDetail(e); if (d.warnings) setServerWarnings(d.warnings); },
  });
  return (
    <Modal open onClose={onClose} title={`Correct mapping of ${ID_LABELS.zk} ${mapping.zk_emp_code}`}>
      <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
        <InlineAlert tone="warning">
          This withdraws the attribution of {mapping.valid_from} – {mapping.valid_to ?? "open"} from {mapping.employee_name ?? mapping.bamboohr_id}.
          Only that period changes; the record is kept in history as superseded.
        </InlineAlert>
        <TextField label="Reason" rows={2} value={reason} onChange={setReason} required />
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={replace} onChange={(e) => setReplace(e.target.checked)} /> Replace with the correct owner
        </label>
        {replace && (
          <div className="space-y-3 rounded-lg border border-dt-border p-3">
            <EmployeePicker value={emp} onChange={(h) => { setEmp(h); setAcked(new Set()); setServerWarnings(null); }} />
            <div className="grid grid-cols-2 gap-2">
              <TextField label="Owned from" type="date" value={from} onChange={setFrom} required />
              <TextField label="Owned until (optional)" type="date" value={to} onChange={setTo} />
            </div>
            <TextField label="Verification evidence" rows={2} value={evidence} onChange={setEvidence} required />
            {emp && isIsoDate(from) && (preview.isError ? <ErrorBox error={preview.error} />
              : preview.isSuccess ? <WarningChecklist warnings={warnings} acked={acked} setAcked={setAcked} /> : null)}
          </div>
        )}
        <ErrorBox error={save.error} />
        <Actions onCancel={onClose} confirm="Confirm correction" disabled={reason.trim().length < MIN_TEXT || !replacementOk} busy={save.isPending} />
      </form>
    </Modal>
  );
}

/* --------------------------------------------------------------- reassign */

const HANDLING: Record<string, string> = {
  leave_unmapped: "Leave that day unmapped (recommended when unsure)",
  attribute_to_new: "Attribute that day to the new owner",
  attribute_to_previous: "Attribute that day to the previous owner",
};

export function ReassignDialog({ mapping, onClose }: { mapping: Mapping; onClose: () => void }) {
  const invalidate = useInvalidate();
  const [d, setD] = useState("");
  const [reason, setReason] = useState("");
  const [emp, setEmp] = useState<DirectoryHit | null>(null);
  const [to, setTo] = useState("");
  const [evidence, setEvidence] = useState("");
  const [acked, setAcked] = useState<Set<string>>(new Set());
  const [serverWarnings, setServerWarnings] = useState<Warning[] | null>(null);
  const [sameDay, setSameDay] = useState<{ events: number; options: string[] } | null>(null);
  const [handling, setHandling] = useState("");
  const warnings = serverWarnings ?? [];
  const ready = Boolean(isIsoDate(d) && (!to || isIsoDate(to)) && emp && reason.trim().length >= MIN_TEXT && evidence.trim().length >= MIN_TEXT
    && warnings.every((w) => acked.has(w.code)) && (!sameDay || handling));
  const save = useMutation({
    mutationFn: () => reassignCode(mapping.zk_emp_code, { site_id: mapping.site_id, effective_from: d, reason,
      same_day_handling: handling || null,
      new: { bamboohr_id: emp!.bamboohr_id, valid_to: to || null, evidence, acknowledged_warnings: [...acked] } }),
    onSuccess: () => { invalidate(); onClose(); },
    onError: (e) => {
      const det = errorDetail(e);
      if (det.error === "REASSIGNMENT_DAY_HAS_ACTIVITY") setSameDay({ events: det.events_on_day ?? 0, options: det.options ?? Object.keys(HANDLING) });
      if (det.warnings) setServerWarnings(det.warnings);
    },
  });
  const pending = save.error && ["REASSIGNMENT_DAY_HAS_ACTIVITY", "WARNINGS_NOT_ACKNOWLEDGED"].includes(errorDetail(save.error).error ?? "");
  return (
    <Modal open onClose={onClose} title={`Reassign ${ID_LABELS.zk} ${mapping.zk_emp_code}`}>
      <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); if (ready) save.mutate(); }}>
        <p className="text-sm">Current owner: {mapping.employee_name ?? mapping.bamboohr_id} (from {mapping.valid_from}). Their attendance before the new owner’s start stays with them.</p>
        <TextField label="New owner from (site-local date)" type="date" value={d} onChange={(v) => { setD(v); setSameDay(null); setHandling(""); }} required />
        <EmployeePicker value={emp} onChange={(h) => { setEmp(h); setAcked(new Set()); setServerWarnings(null); }} />
        <TextField label="New owner until (optional)" type="date" value={to} onChange={setTo} />
        <TextField label="Reason" rows={2} value={reason} onChange={setReason} required />
        <TextField label="Verification evidence for the new owner" rows={2} value={evidence} onChange={setEvidence} required />
        {sameDay && (
          <fieldset className="space-y-1 rounded-lg border border-dt-amber/50 bg-dt-amber/10 p-3 text-sm">
            <legend className="px-1 font-medium">{sameDay.events} punch(es) on {d} cannot be split automatically — choose:</legend>
            {sameDay.options.map((o) => (
              <label key={o} className="flex items-center gap-2"><input type="radio" name="handling" checked={handling === o} onChange={() => setHandling(o)} />{HANDLING[o] ?? o}</label>
            ))}
          </fieldset>
        )}
        {serverWarnings && <WarningChecklist warnings={warnings} acked={acked} setAcked={setAcked} />}
        {!pending && <ErrorBox error={save.error} />}
        <Actions onCancel={onClose} confirm={sameDay || serverWarnings ? "Confirm reassignment" : "Check and reassign"} disabled={!ready} busy={save.isPending} />
      </form>
    </Modal>
  );
}

/* ----------------------------------------------------------------- reject */

export function RejectDialog({ siteId, code, onClose }: { siteId: string; code: string; onClose: () => void }) {
  const invalidate = useInvalidate();
  const [emp, setEmp] = useState<DirectoryHit | null>(null);
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [reason, setReason] = useState("");
  const save = useMutation({
    mutationFn: () => rejectAssociation({ site_id: siteId, zk_emp_code: code, bamboohr_id: emp!.bamboohr_id, reason,
      applies_from: from || null, applies_to: to || null }),
    onSuccess: () => { invalidate(); onClose(); },
  });
  return (
    <Modal open onClose={onClose} title={`Record: ${ID_LABELS.zk} ${code} is NOT this person`}>
      <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
        <p className="text-sm text-dt-text-secondary">A rejection never attributes attendance. It stops this pairing being hinted or mapped for the period (leave dates empty for all history).</p>
        <EmployeePicker value={emp} onChange={setEmp} />
        <div className="grid grid-cols-2 gap-2">
          <TextField label="Applies from (optional)" type="date" value={from} onChange={setFrom} />
          <TextField label="Applies until (optional)" type="date" value={to} onChange={setTo} />
        </div>
        <TextField label="Reason" rows={2} value={reason} onChange={setReason} required />
        <ErrorBox error={save.error} />
        <Actions onCancel={onClose} confirm="Record rejection"
          disabled={!emp || reason.trim().length < MIN_TEXT || (!!from && !isIsoDate(from)) || (!!to && !isIsoDate(to))} busy={save.isPending} />
      </form>
    </Modal>
  );
}

export function WithdrawDialog({ rejection, onClose }: { rejection: Rejection; onClose: () => void }) {
  const invalidate = useInvalidate();
  const [reason, setReason] = useState("");
  const save = useMutation({ mutationFn: () => withdrawRejection(rejection.id, reason), onSuccess: () => { invalidate(); onClose(); } });
  return (
    <Modal open onClose={onClose} title="Withdraw rejection">
      <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
        <p className="text-sm">{ID_LABELS.zk} <span className="font-mono">{rejection.zk_emp_code}</span> ≠ {ID_LABELS.bhr} <span className="font-mono">{rejection.bamboohr_id}</span></p>
        <TextField label="Reason" rows={2} value={reason} onChange={setReason} required />
        <ErrorBox error={save.error} />
        <Actions onCancel={onClose} confirm="Withdraw" disabled={reason.trim().length < MIN_TEXT} busy={save.isPending} />
      </form>
    </Modal>
  );
}

/* --------------------------------------------------------------- read-only */

export function HistoryDialog({ mappingId, onClose }: { mappingId: number; onClose: () => void }) {
  const q = useQuery({ queryKey: ["onsite-identity-mapping", mappingId], queryFn: () => getMapping(mappingId) });
  return (
    <Modal open onClose={onClose} title={`Mapping #${mappingId} history`}>
      {!q.data ? <SkeletonRows rows={3} /> : (
        <div className="space-y-3 text-sm">
          <p>{ID_LABELS.zk} <span className="font-mono">{q.data.zk_emp_code}</span> → {q.data.employee_name ?? "—"} ({ID_LABELS.bhr} <span className="font-mono">{q.data.bamboohr_id}</span>), {q.data.valid_from} – {q.data.valid_to ?? "open"} · <ToneBadge tone={q.data.status === "VERIFIED" ? "success" : "neutral"}>{q.data.status}</ToneBadge></p>
          <p className="text-dt-text-secondary">Evidence: {q.data.evidence}</p>
          <ol className="space-y-2 border-l-2 border-dt-border pl-3">
            {q.data.history.map((h) => (
              <li key={h.id}><span className="font-medium">{h.action}</span> · user {h.actor_user_id} · {h.at ? new Date(h.at).toLocaleString() : "—"}{h.note ? ` — ${h.note}` : ""}</li>
            ))}
          </ol>
        </div>
      )}
    </Modal>
  );
}

export function CodeDialog({ siteId, code, onClose }: { siteId: string; code: string; onClose: () => void }) {
  const q = useQuery({ queryKey: ["onsite-identity-code", siteId, code], queryFn: () => getCodeDetail(code, { site_id: siteId }) });
  return (
    <Modal open onClose={onClose} title={`${ID_LABELS.zk} ${code}`}>
      {!q.data ? <SkeletonRows rows={4} /> : (
        <div className="space-y-3 text-sm">
          <section>
            <h3 className="font-medium">Ownership periods</h3>
            {q.data.mappings.length ? (
              <ul className="list-disc pl-5">{q.data.mappings.map((m) => (
                <li key={m.id}>{m.employee_name ?? m.bamboohr_id} ({ID_LABELS.bhr} {m.bamboohr_id}) · {m.valid_from} – {m.valid_to ?? "open"} · {m.status}</li>
              ))}</ul>
            ) : <p className="text-dt-text-secondary">Never verified.</p>}
          </section>
          {q.data.hint_employee_number_matches.length > 0 && (
            <p className="text-dt-text-secondary">Unverified hint (Employee Number equals this ID — not evidence): {q.data.hint_employee_number_matches.map((h) => h.display_name ?? h.bamboohr_id).join(", ")}</p>
          )}
          <section>
            <h3 className="font-medium">Activity by day</h3>
            <div className="max-h-64 overflow-y-auto">
              <table className="w-full text-xs">
                <thead><tr className="text-left text-dt-text-secondary"><th>Date</th><th>Punches</th><th>{ID_LABELS.mapping}</th><th>Attributed to</th></tr></thead>
                <tbody>{q.data.days.slice().reverse().map((d) => (
                  <tr key={d.local_date} className="border-t border-dt-border"><td>{d.local_date}</td><td>{d.events}</td>
                    <td>{d.mapping_status}</td><td>{d.employee_name ?? d.bamboohr_id ?? "—"}</td></tr>
                ))}</tbody>
              </table>
            </div>
          </section>
        </div>
      )}
    </Modal>
  );
}
