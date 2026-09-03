"use client";

import { useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { ApplicationsView } from "@/components/talent/ApplicationsView";
import { LoadingState } from "@dijione/design-system";

function ApplicationsPageInner() {
  const searchParams = useSearchParams();
  return (
    <ApplicationsView
      initialSearch={searchParams.get("search") ?? ""}
      initialStatus={searchParams.get("status") ?? ""}
    />
  );
}

export default function ApplicationsPage() {
  return (
    <Suspense fallback={<LoadingState />}>
      <ApplicationsPageInner />
    </Suspense>
  );
}
