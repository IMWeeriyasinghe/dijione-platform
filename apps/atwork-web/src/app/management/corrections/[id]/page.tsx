"use client";

import Link from "next/link";
import { use, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, Card, FormField, LoadingState, Modal, PageHeader, StatusBadge, Textarea } from "@dijione/design-system";
import { CORRECTION_TITLE, CorrectionComparison, Notice, Page, QueryError, RequirePermission } from "@/components/ui";
import { errorMessage, management } from "@/lib/api";
import { dateTime } from "@/lib/format";
import { hasPermission, PERM, useAtworkScope } from "@/lib/atwork-scope";
import { useDisplay } from "@/lib/hooks";

function Screen({ id }: { id: string }) {
  const { scope } = useAtworkScope();
  const { zone, format } = useDisplay();
  const client = useQueryClient();
  const [dialog, setDialog] = useState<"approve" | "reject" | null>(null);
  const [text, setText] = useState("");
  const query = useQuery({ queryKey: ["atwork", "correction", id], queryFn: () => management.correction(id), retry: false });
  const decide = useMutation({
    mutationFn: () => (dialog === "approve" ? management.approve(id, text.trim()) : management.reject(id, text.trim())),
    onSuccess: () => { setDialog(null); setText(""); },
    onSettled: () => client.invalidateQueries({ queryKey: ["atwork"] }),
  });
  if (query.isLoading) return <LoadingState />;
  if (!query.data) return <QueryError error={query.error} retry={() => query.refetch()} />;
  const c = query.data;
  const canAct = c.can_decide && hasPermission(scope, PERM.APPROVE);
  const own = c.status === "PENDING" && !c.can_decide && hasPermission(scope, PERM.APPROVE);
  return (
    <>
      <PageHeader title={CORRECTION_TITLE[c.kind]} description={`${c.employee_name} · requested ${dateTime(c.created_at, zone, format)}`} action={<StatusBadge status={c.status} />} />
      {decide.isError && !dialog && <Notice tone="error">{errorMessage(decide.error)}</Notice>}
      {decide.isSuccess && <Notice tone="success">The decision was saved.</Notice>}
      {own && <Notice tone="info">This is your own request, so another manager must decide it.</Notice>}
      <Card className="p-5">
        <p className="text-sm"><span className="text-dt-text-secondary">Reason: </span>{c.reason}</p>
        <div className="mt-4"><CorrectionComparison item={c} zone={zone} format={format} /></div>
        {c.reviewer_name && <p className="mt-4 text-sm"><span className="text-dt-text-secondary">Decided by {c.reviewer_name}{c.reviewed_at ? ` on ${dateTime(c.reviewed_at, zone, format)}` : ""}{c.decision_note ? ": " : ""}</span>{c.decision_note}</p>}
        {canAct && <div className="mt-5 flex flex-wrap gap-2"><Button onClick={() => { decide.reset(); setDialog("approve"); }}>Approve</Button><Button variant="danger" onClick={() => { decide.reset(); setDialog("reject"); }}>Reject</Button></div>}
      </Card>
      <Link href="/management/corrections" className="mt-6 inline-block text-sm font-medium text-dt-burnt-orange underline underline-offset-2">Back to Corrections</Link>
      <Modal open={dialog !== null} onClose={() => !decide.isPending && setDialog(null)} title={dialog === "approve" ? "Approve this correction?" : "Reject this correction?"}>
        <form onSubmit={(e) => { e.preventDefault(); if (!decide.isPending) decide.mutate(); }} className="space-y-4">
          {decide.isError && <Notice tone="error">{errorMessage(decide.error)}</Notice>}
          <p className="text-sm text-dt-text-secondary">{dialog === "approve" ? "The official record changes now. The original values stay in the audit history." : "The official record will not change."}</p>
          <FormField label={dialog === "approve" ? "Note (optional)" : "Rejection reason"} htmlFor="decision" required={dialog === "reject"}><Textarea id="decision" value={text} maxLength={1000} onChange={(e) => setText(e.target.value)} /></FormField>
          <Button type="submit" variant={dialog === "approve" ? "primary" : "danger"} loading={decide.isPending} disabled={dialog === "reject" && text.trim().length < 5}>{dialog === "approve" ? "Approve" : "Reject"}</Button>
        </form>
      </Modal>
    </>
  );
}

export default function CorrectionPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  return <Page><RequirePermission permission={[PERM.MANAGEMENT, PERM.REVIEW]} title="Correction review access required"><Screen id={id} /></RequirePermission></Page>;
}
