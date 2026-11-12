"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import {
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Textarea,
} from "@dijione/design-system";
import type { TimelineEntryOut } from "@dijione/contracts";
import { getOrderTimeline, postOrderMessage } from "@/lib/api";

const KIND_LABEL: Record<string, string> = {
  message: "Message",
  email: "Email",
  event: "System",
  issue: "Issue",
};

function EntryRow({ e }: { e: TimelineEntryOut }) {
  const dir =
    e.direction === "INBOUND" ? "from supplier" : e.direction === "OUTBOUND" ? "to supplier" : null;
  return (
    <li className="border-l-2 border-dt-border pl-3">
      <div className="flex flex-wrap items-baseline gap-x-2 text-sm">
        <span className="font-medium text-dt-text-primary">{e.title}</span>
        {e.channel && (
          <span className="rounded bg-dt-surface-warm px-1.5 py-0.5 text-[11px] text-dt-text-secondary">
            {e.channel}
          </span>
        )}
        {dir && <span className="text-[11px] text-dt-text-secondary">{dir}</span>}
      </div>
      {e.body && <p className="mt-0.5 whitespace-pre-wrap text-sm text-dt-text-secondary">{e.body}</p>}
      <p className="mt-0.5 text-xs text-dt-text-secondary">
        {e.at ? new Date(e.at).toLocaleString() : "—"} · {KIND_LABEL[e.kind] ?? e.kind}
      </p>
    </li>
  );
}

export function OrderTimeline({ orderId }: { orderId: number }) {
  const qc = useQueryClient();
  const { data } = useQuery({
    queryKey: ["order-timeline", orderId],
    queryFn: () => getOrderTimeline(orderId),
  });
  const [draft, setDraft] = useState("");
  const [alsoEmail, setAlsoEmail] = useState(false);

  const send = useMutation({
    mutationFn: () => postOrderMessage(orderId, draft, { also_email: alsoEmail }),
    onSuccess: () => {
      setDraft("");
      setAlsoEmail(false);
      qc.invalidateQueries({ queryKey: ["order-timeline", orderId] });
      qc.invalidateQueries({ queryKey: ["order", orderId] });
    },
  });

  const entries = data?.entries ?? [];

  return (
    <Card>
      <CardHeader>
        <CardTitle>Timeline</CardTitle>
      </CardHeader>
      <CardContent>
        {entries.length === 0 ? (
          <p className="text-sm text-dt-text-secondary">No activity yet.</p>
        ) : (
          <ol className="flex flex-col gap-4">
            {entries.map((e, i) => (
              <EntryRow key={i} e={e} />
            ))}
          </ol>
        )}

        <div className="mt-5 flex flex-col gap-2 border-t border-dt-border pt-4">
          <Textarea
            value={draft}
            onChange={(ev) => setDraft(ev.target.value)}
            placeholder="Post a message to the supplier on this order…"
            rows={2}
          />
          <div className="flex items-center justify-between">
            <label className="flex items-center gap-2 text-xs text-dt-text-secondary">
              <input type="checkbox" checked={alsoEmail} onChange={(ev) => setAlsoEmail(ev.target.checked)} />
              Also email the supplier a copy
            </label>
            <Button
              size="sm"
              loading={send.isPending}
              disabled={draft.trim() === ""}
              onClick={() => send.mutate()}
            >
              Send
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
