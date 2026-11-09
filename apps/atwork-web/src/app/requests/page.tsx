"use client";

import Link from "next/link";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, Card, EmptyState, FormField, LoadingState, PageHeader, Select, StatusBadge } from "@dijione/design-system";
import { CORRECTION_TITLE, CorrectionComparison, Notice, Page, Pager, QueryError, RequirePermission } from "@/components/ui";
import { corrections, errorMessage } from "@/lib/api";
import { dateTime } from "@/lib/format";
import { PERM } from "@/lib/atwork-scope";
import { useDisplay } from "@/lib/hooks";

const LIMIT = 20;

function Requests() {
  const client = useQueryClient();
  const { zone, format } = useDisplay();
  const [status, setStatus] = useState("");
  const [offset, setOffset] = useState(0);
  const query = useQuery({ queryKey: ["atwork", "requests", status, offset], queryFn: () => corrections.list({ status, limit: LIMIT, offset }) });
  const withdraw = useMutation({ mutationFn: corrections.withdraw, onSettled: () => client.invalidateQueries({ queryKey: ["atwork"] }) });
  return (
    <>
      <PageHeader title="My Requests" description="Corrections you have asked Management to approve." action={<span className="flex flex-wrap gap-2"><Link href="/attendance"><Button variant="secondary">Correct a session</Button></Link><Link href="/requests/new"><Button>Request missing session</Button></Link></span>} />
      {withdraw.isError && <Notice tone="error">{errorMessage(withdraw.error)}</Notice>}
      {withdraw.isSuccess && <Notice tone="success">Your request was withdrawn.</Notice>}
      <div className="mb-4 max-w-xs">
        <FormField label="Status" htmlFor="status-filter">
          <Select id="status-filter" value={status} onChange={(e) => { setStatus(e.target.value); setOffset(0); }}>
            <option value="">All</option><option value="PENDING">Pending</option><option value="APPROVED">Approved</option><option value="REJECTED">Rejected</option><option value="WITHDRAWN">Withdrawn</option>
          </Select>
        </FormField>
      </div>
      {query.isLoading ? <LoadingState /> : !query.data ? <QueryError error={query.error} retry={() => query.refetch()} /> : query.data.items.length === 0 ? (
        <EmptyState title="No correction requests" description="Open a session to request a correction, or request a missing session." />
      ) : (
        <div className="space-y-3">
          {query.data.items.map((item) => (
            <Card key={item.id} className="p-5">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h2 className="text-base font-semibold">{CORRECTION_TITLE[item.kind]}</h2>
                <StatusBadge status={item.status} />
              </div>
              <p className="mt-1 text-xs text-dt-text-secondary">Requested {dateTime(item.created_at, zone, format)}</p>
              <p className="mt-3 text-sm"><span className="text-dt-text-secondary">Reason: </span>{item.reason}</p>
              <div className="mt-3"><CorrectionComparison item={item} zone={zone} format={format} /></div>
              {item.decision_note && <p className="mt-3 text-sm"><span className="text-dt-text-secondary">{item.reviewer_name}: </span>{item.decision_note}</p>}
              {item.status === "PENDING" && <Button className="mt-4" size="sm" variant="secondary" loading={withdraw.isPending && withdraw.variables === item.id} disabled={withdraw.isPending} onClick={() => withdraw.mutate(item.id)}>Withdraw</Button>}
            </Card>
          ))}
          <Pager total={query.data.total} limit={LIMIT} offset={offset} onChange={setOffset} />
        </div>
      )}
    </>
  );
}

export default function RequestsPage() {
  return <Page><RequirePermission permission={PERM.REQUEST_OWN} title="Correction access required"><Requests /></RequirePermission></Page>;
}
