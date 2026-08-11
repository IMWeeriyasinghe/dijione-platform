"use client";

import { useSearchParams } from "next/navigation";
import { Suspense, use } from "react";
import { RequestDetail } from "@/components/talent/RequestDetail";
import { LoadingState } from "@/components/ui/States";

const VALID_TABS = ["Overview", "Candidates", "Interviews", "Messages", "Documents"] as const;

function RequestDetailPageInner({ id }: { id: string }) {
  const searchParams = useSearchParams();
  const tabParam = searchParams.get("tab");
  const initialTab = VALID_TABS.find((t) => t.toLowerCase() === tabParam?.toLowerCase());
  return <RequestDetail requestId={Number(id)} initialTab={initialTab} />;
}

export default function RequestDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  return (
    <Suspense fallback={<LoadingState />}>
      <RequestDetailPageInner id={id} />
    </Suspense>
  );
}
