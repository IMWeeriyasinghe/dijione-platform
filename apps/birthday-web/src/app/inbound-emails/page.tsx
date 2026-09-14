"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import {
  Button,
  Card,
  CardContent,
  EmptyState,
  ErrorState,
  FormField,
  Input,
  LoadingState,
  PageHeader,
} from "@dijione/design-system";
import { dismissUnmatchedEmail, linkUnmatchedEmail, listUnmatchedEmails } from "@/lib/api";

export default function UnmatchedEmailsPage() {
  const qc = useQueryClient();
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["unmatched-emails"],
    queryFn: () => listUnmatchedEmails(),
  });
  const [linkFor, setLinkFor] = useState<number | null>(null);
  const [orderRef, setOrderRef] = useState("");
  const [raiseIssue, setRaiseIssue] = useState(false);

  const invalidate = () => qc.invalidateQueries({ queryKey: ["unmatched-emails"] });
  const linkMut = useMutation({
    mutationFn: (id: number) => {
      const v = orderRef.trim();
      const asNum = Number(v);
      return linkUnmatchedEmail(id, {
        ...(Number.isInteger(asNum) && String(asNum) === v
          ? { order_id: asNum }
          : { order_reference: v }),
        raise_issue: raiseIssue,
      });
    },
    onSuccess: () => {
      setLinkFor(null);
      setOrderRef("");
      setRaiseIssue(false);
      invalidate();
    },
  });
  const dismissMut = useMutation({
    mutationFn: (id: number) => dismissUnmatchedEmail(id),
    onSuccess: invalidate,
  });

  if (isLoading) return <LoadingState label="Loading unmatched emails…" />;
  if (isError || !data) return <ErrorState onRetry={() => refetch()} />;

  return (
    <div>
      <PageHeader
        title="Unmatched supplier email"
        description="Supplier emails that could not be safely correlated to an order. Link one to an order, or dismiss it. Nothing here has touched an order."
      />
      {data.length === 0 ? (
        <EmptyState title="Nothing to review" description="All inbound supplier email has been correlated." />
      ) : (
        <div className="flex flex-col gap-4">
          {data.map((e) => (
            <Card key={e.id}>
              <CardContent className="flex flex-col gap-2">
                <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
                  <span className="font-medium text-dt-text-primary">{e.from_address || "(no sender)"}</span>
                  <span className="text-dt-text-secondary">
                    {e.received_at ? new Date(e.received_at).toLocaleString() : "—"}
                  </span>
                </div>
                <p className="text-sm font-medium text-dt-text-primary">{e.subject || "(no subject)"}</p>
                <p className="whitespace-pre-wrap text-sm text-dt-text-secondary">{e.body_preview}</p>
                <p className="text-xs text-dt-text-secondary">Reason: {e.reason}</p>
                {linkFor === e.id ? (
                  <div className="mt-1 flex flex-wrap items-end gap-3 rounded-lg border border-dt-border bg-dt-surface-warm p-3">
                    <FormField label="Order reference or ID" htmlFor={`oref-${e.id}`}>
                      <Input
                        id={`oref-${e.id}`}
                        value={orderRef}
                        onChange={(ev) => setOrderRef(ev.target.value)}
                        placeholder="e.g. BDAY-EMP239-2026-00001"
                        className="w-full sm:w-64"
                      />
                    </FormField>
                    <label className="flex items-center gap-2 text-sm text-dt-text-secondary">
                      <input type="checkbox" checked={raiseIssue} onChange={(ev) => setRaiseIssue(ev.target.checked)} />
                      Also raise an issue
                    </label>
                    <Button
                      size="sm"
                      loading={linkMut.isPending}
                      disabled={!orderRef.trim()}
                      onClick={() => linkMut.mutate(e.id)}
                    >
                      Link
                    </Button>
                    <Button size="sm" variant="secondary" onClick={() => setLinkFor(null)}>
                      Cancel
                    </Button>
                  </div>
                ) : (
                  <div className="mt-1 flex gap-2">
                    <Button size="sm" onClick={() => setLinkFor(e.id)}>
                      Link to an order
                    </Button>
                    <Button
                      size="sm"
                      variant="secondary"
                      loading={dismissMut.isPending}
                      onClick={() => dismissMut.mutate(e.id)}
                    >
                      Dismiss
                    </Button>
                  </div>
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
