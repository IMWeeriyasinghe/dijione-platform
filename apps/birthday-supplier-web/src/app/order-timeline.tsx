"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Button, Card, CardContent, CardHeader, CardTitle, Textarea } from "@dijione/design-system";
import type { TimelineEntryOut } from "@dijione/contracts";
import { getPortalOrderTimeline, postPortalOrderMessage } from "@/lib/api";
import { useSupplierAuth } from "@/lib/supplier-auth";
import { usePortalMe } from "@/lib/portal-me";

export function OrderTimeline({ orderId }: { orderId: number }) {
  const { token } = useSupplierAuth();
  const readOnly = usePortalMe()?.read_only ?? false;
  const qc = useQueryClient();
  const { data } = useQuery({
    queryKey: ["portal-order-timeline", orderId],
    queryFn: () => getPortalOrderTimeline(token!, orderId),
    enabled: !!token,
  });
  const [draft, setDraft] = useState("");

  const send = useMutation({
    mutationFn: () => postPortalOrderMessage(token!, orderId, draft),
    onSuccess: () => {
      setDraft("");
      qc.invalidateQueries({ queryKey: ["portal-order-timeline", orderId] });
    },
  });

  const entries: TimelineEntryOut[] = data?.entries ?? [];

  return (
    <Card className="mt-6">
      <CardHeader>
        <CardTitle>Order activity & messages</CardTitle>
      </CardHeader>
      <CardContent>
        {entries.length === 0 ? (
          <p className="text-sm text-dt-text-secondary">No activity yet.</p>
        ) : (
          <ol className="flex flex-col gap-4">
            {entries.map((e, i) => (
              <li key={i} className="border-l-2 border-dt-border pl-3">
                <div className="flex flex-wrap items-baseline gap-x-2 text-sm">
                  <span className="font-medium text-dt-text-primary">{e.title}</span>
                  {e.channel && (
                    <span className="rounded bg-dt-surface-warm px-1.5 py-0.5 text-[11px] text-dt-text-secondary">
                      {e.channel}
                    </span>
                  )}
                </div>
                {e.body && (
                  <p className="mt-0.5 whitespace-pre-wrap text-sm text-dt-text-secondary">{e.body}</p>
                )}
                <p className="mt-0.5 text-xs text-dt-text-secondary">
                  {e.at ? new Date(e.at).toLocaleString() : "—"}
                </p>
              </li>
            ))}
          </ol>
        )}
        {!readOnly && (
          <div className="mt-5 flex flex-col gap-2 border-t border-dt-border pt-4">
            <Textarea
              value={draft}
              onChange={(ev) => setDraft(ev.target.value)}
              placeholder="Send a message to Dijital Team about this order…"
              rows={2}
            />
            <div className="flex justify-end">
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
        )}
      </CardContent>
    </Card>
  );
}
