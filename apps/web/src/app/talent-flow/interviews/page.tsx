"use client";

import { useTalentScope } from "@/lib/auth-context";
import { PageHeader } from "@/components/ui/PageHeader";
import { InterviewList } from "@/components/talent/InterviewList";

export default function InterviewsPage() {
  const scope = useTalentScope();
  if (!scope) return null;

  return (
    <div>
      <PageHeader
        title={scope.isStaff ? "Interview Manager" : "Interviews"}
        description={
          scope.isStaff
            ? "Cross-client view of every scheduled and completed interview."
            : "Upcoming and past interviews for your talent requests."
        }
      />
      <InterviewList />
    </div>
  );
}
