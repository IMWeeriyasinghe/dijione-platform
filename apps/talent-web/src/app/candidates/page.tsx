"use client";

import { useTalentScope } from "@dijione/auth-client";
import { CandidatePoolView } from "@/components/talent/CandidatePoolView";
import { ClientCandidatesOverview } from "@/components/talent/ClientCandidatesOverview";

export default function CandidatesPage() {
  const scope = useTalentScope();
  if (!scope) return null;
  return scope.isStaff ? <CandidatePoolView /> : <ClientCandidatesOverview />;
}
