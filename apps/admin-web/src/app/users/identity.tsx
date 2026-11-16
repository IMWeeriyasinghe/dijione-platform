"use client";

import type { AdminUserOut } from "@dijione/contracts";
import { useAuthorizedImage } from "@dijione/auth-client";
import { Avatar, StatusBadge } from "@dijione/design-system";

/** A person's Microsoft 365 photo (served by DijiOne, never straight from Graph), or their initials. */
export function EmployeeAvatar({ path, name, size = 32 }: { path: string | null; name: string; size?: number }) {
  const src = useAuthorizedImage(path);
  return <Avatar name={name} size={size} src={src} />;
}

export const EMPLOYEE_RECORD_LABEL: Record<string, string> = {
  MATCHED: "In BambooHR",
  NOT_FOUND: "Not in BambooHR",
  UNKNOWN: "BambooHR unknown",
  LEGACY: "HR reconciliation pending",
};

const EMPLOYEE_RECORD_STATUS: Record<string, string> = {
  MATCHED: "COMPLETED",
  NOT_FOUND: "ERROR",
  UNKNOWN: "NOT_STARTED",
  LEGACY: "PENDING",
};

export function EmployeeRecordBadge({ status }: { status: string | null | undefined }) {
  if (!status) return null;
  return <StatusBadge status={EMPLOYEE_RECORD_STATUS[status] ?? "NOT_STARTED"} label={EMPLOYEE_RECORD_LABEL[status] ?? status} />;
}

/** Whether the profile is directory verified, matched to an employee record, and has signed in yet. */
export function IdentityBadges({ user }: { user: AdminUserOut }) {
  return (
    <div className="flex flex-wrap items-center gap-1.5" data-testid="identity-badges">
      {user.directory_verified ? (
        <StatusBadge status="COMPLETED" label={user.verification_source === "DIRECTORY" ? "Directory verified" : "Verified at sign-in"} />
      ) : (
        <StatusBadge status="PENDING" label="Awaiting directory verification" />
      )}
      <EmployeeRecordBadge status={user.employee_record} />
      <StatusBadge status={user.signed_in ? "SYNCED" : "NOT_STARTED"} label={user.signed_in ? "Signed in" : "Provisioned, not yet signed in"} />
    </div>
  );
}
