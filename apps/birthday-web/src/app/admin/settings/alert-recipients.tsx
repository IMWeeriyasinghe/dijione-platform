"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Button, FormField } from "@dijione/design-system";
import { updateConfig } from "@/lib/api";

const EMAIL = /^[^@\s,;]+@[^@\s,;]+\.[^@\s,;]+$/;
export const MAX_ALERT_RECIPIENTS = 20;

export function parseRecipients(raw: string): string[] {
  const out: string[] = [];
  for (const part of raw.split(/[,;\n]/)) {
    const email = part.trim().toLowerCase();
    if (email && !out.includes(email)) out.push(email);
  }
  return out;
}

export function recipientsError(raw: string): string | null {
  const emails = parseRecipients(raw);
  const bad = emails.filter((e) => !EMAIL.test(e));
  if (bad.length) return `Not a valid email address: ${bad.slice(0, 3).join(", ")}`;
  if (emails.length > MAX_ALERT_RECIPIENTS) return `At most ${MAX_ALERT_RECIPIENTS} recipients.`;
  return null;
}

/** P&C operational alert recipients: who is emailed when the supplier sends
 * a message, reports an issue or cannot fulfil an order. Saved on its own so
 * it can never change the go-live settings. */
export function AlertRecipientsSection({ saved }: { saved: string | null }) {
  const qc = useQueryClient();
  const [draft, setDraft] = useState<string | null>(null);
  const value = draft ?? (saved ?? "");
  const error = recipientsError(value);
  const dirty = parseRecipients(value).join("\n") !== parseRecipients(saved ?? "").join("\n");

  const save = useMutation({
    mutationFn: () => updateConfig({ ops_alert_recipients: parseRecipients(value).join("\n") || null }),
    onSuccess: () => {
      setDraft(null);
      qc.invalidateQueries({ queryKey: ["birthday-config"] });
    },
  });

  return (
    <section className="rounded-xl border border-dt-border bg-dt-surface p-5" data-testid="alert-recipients">
      <h2 className="text-base font-semibold text-dt-text-primary">Supplier activity alerts</h2>
      <p className="mt-1 text-sm text-dt-text-secondary">
        These people are emailed when the supplier sends a message, reports an issue or cannot fulfil an
        order in the Supplier Portal. The activity also stays on the order timeline.
      </p>
      <div className="mt-4">
        <FormField
          label="Alert recipients"
          htmlFor="alert-recipients"
          hint={error ?? "One email address per line (or separated by commas). Leave empty to turn email alerts off."}
        >
          <textarea
            id="alert-recipients"
            rows={3}
            className="w-full rounded-lg border border-dt-border px-3 py-2 text-sm"
            value={value}
            aria-invalid={!!error}
            onChange={(e) => setDraft(e.target.value)}
          />
        </FormField>
      </div>
      {save.isError && <p className="mt-2 text-sm text-dt-danger">Could not save the recipients.</p>}
      <div className="mt-3 flex justify-end">
        <Button size="sm" disabled={!dirty || !!error} loading={save.isPending} onClick={() => save.mutate()}>
          Save recipients
        </Button>
      </div>
    </section>
  );
}
