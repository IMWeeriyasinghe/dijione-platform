"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { getUpcomingBirthdays } from "@/lib/api";
import type { UpcomingBirthdayItem } from "@dijione/contracts";
import {
  ErrorState,
  LoadingState,
  Pagination,
  PageHeader,
  SearchInput,
  Select,
  SortableTh,
  StatusBadge,
  Table,
  Td,
  Th,
  Thead,
  Tr,
  EmptyState,
  useSortToggle,
  type SortDirection,
} from "@dijione/design-system";

const DAYS_OPTIONS = [7, 14, 30, 60];
const PAGE_SIZE = 25;

// Any ineligible reason other than FUTURE_STARTER (INACTIVE_EMPLOYEE,
// EMPLOYMENT_ENDED, MISSING_HIRE_DATE, MISSING_BIRTHDAY,
// INVALID_EMPLOYEE_DATA) falls into the "Not Eligible" group by default in
// groupFor() below — no explicit list needed here.
const NEEDS_ATTENTION_ORDER_STATUSES = new Set(["REQUIRES_ATTENTION", "ON_HOLD"]);
const NEEDS_ATTENTION_ADDRESS_STATUSES = new Set(["NEEDS_UPDATE", "VERIFICATION_REQUESTED"]);

type Group = "ELIGIBLE" | "FUTURE_STARTER" | "NOT_ELIGIBLE" | "NEEDS_ATTENTION";

// Display-only mirror of birthday-api's directory_service.group_for — the
// actual filtering (Phase-Next §4) now happens server-side via the
// `filter` query param, this is purely for the per-row badge label.
function groupFor(item: UpcomingBirthdayItem): Group {
  if (
    item.eligible &&
    (NEEDS_ATTENTION_ORDER_STATUSES.has(item.cake_order_status) ||
      (item.address_verification_status != null &&
        NEEDS_ATTENTION_ADDRESS_STATUSES.has(item.address_verification_status)))
  ) {
    return "NEEDS_ATTENTION";
  }
  if (item.eligible) return "ELIGIBLE";
  if (item.eligibility_reason === "FUTURE_STARTER") return "FUTURE_STARTER";
  return "NOT_ELIGIBLE";
}

const GROUP_LABELS: Record<Group, string> = {
  ELIGIBLE: "Upcoming & Eligible",
  FUTURE_STARTER: "Future Starter",
  NOT_ELIGIBLE: "Not Eligible",
  NEEDS_ATTENTION: "Needs Attention",
};

const GROUP_FILTER_OPTIONS: Array<Group | "ALL"> = [
  "ALL",
  "ELIGIBLE",
  "NEEDS_ATTENTION",
  "FUTURE_STARTER",
  "NOT_ELIGIBLE",
];

// Sourced live from BambooHR (active employees only, filtered server-side
// in birthday-api) — not from BirthdayOrder rows, so an employee shows up
// here even before the daily detection scan has created a cake order for
// them. Eligibility, search, group filtering, sorting and pagination are
// all computed/applied server-side (Phase-Next §4) — this page only
// renders the result.
export default function UpcomingPage() {
  const [days, setDays] = useState(30);
  const [groupFilter, setGroupFilter] = useState<Group | "ALL">("ALL");
  const [search, setSearch] = useState("");
  const [sortBy, setSortBy] = useState<string | null>(null);
  const [sortDirection, setSortDirection] = useState<SortDirection>("asc");
  const [page, setPage] = useState(1);

  const params = {
    days,
    search: search || undefined,
    filter: groupFilter !== "ALL" ? groupFilter : undefined,
    sort_by: sortBy || undefined,
    sort_direction: sortDirection,
    page,
    page_size: PAGE_SIZE,
  };

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["birthday-upcoming-birthdays", params],
    queryFn: () => getUpcomingBirthdays(params),
  });

  const toggleSort = useSortToggle(sortBy, sortDirection, setSortBy, setSortDirection);
  const birthdays = data?.birthdays ?? [];

  function resetAndSet<T>(setter: (v: T) => void, value: T) {
    setPage(1);
    setter(value);
  }

  return (
    <div>
      <PageHeader
        title="Upcoming Birthdays"
        description="Active employees with birthdays approaching, sourced from BambooHR, with eligibility and address-verification status for each cake order."
        action={
          <div className="flex gap-2">
            <Select
              value={groupFilter}
              onChange={(e) => resetAndSet(setGroupFilter, e.target.value as Group | "ALL")}
              className="w-auto"
            >
              <option value="ALL">All groups</option>
              {GROUP_FILTER_OPTIONS.filter((g) => g !== "ALL").map((g) => (
                <option key={g} value={g}>
                  {GROUP_LABELS[g as Group]}
                </option>
              ))}
            </Select>
            <Select value={days} onChange={(e) => resetAndSet(setDays, Number(e.target.value))} className="w-auto">
              {DAYS_OPTIONS.map((d) => (
                <option key={d} value={d}>
                  Next {d} days
                </option>
              ))}
            </Select>
          </div>
        }
      />

      <SearchInput
        value={search}
        onChange={(v) => resetAndSet(setSearch, v)}
        placeholder="Search employee number or name…"
        className="mb-4 max-w-md"
      />

      {isLoading ? (
        <LoadingState label="Loading upcoming birthdays…" />
      ) : isError || !data ? (
        <ErrorState onRetry={() => refetch()} />
      ) : birthdays.length === 0 ? (
        <EmptyState
          title="No matches"
          description={`No employees found within the next ${days} days for the current search/filter.`}
        />
      ) : (
        <>
          <Table>
            <Thead>
              <Tr>
                <SortableTh
                  label="Employee"
                  sortKey="employee_number"
                  activeSortBy={sortBy}
                  sortDirection={sortDirection}
                  onSort={toggleSort}
                />
                <Th>Birthday</Th>
                <SortableTh
                  label="Days Until"
                  sortKey="days_until_birthday"
                  activeSortBy={sortBy}
                  sortDirection={sortDirection}
                  onSort={toggleSort}
                />
                <SortableTh
                  label="Hire Date"
                  sortKey="hire_date"
                  activeSortBy={sortBy}
                  sortDirection={sortDirection}
                  onSort={toggleSort}
                />
                <Th>Eligibility</Th>
                <Th>Location</Th>
                <Th>Address Verification</Th>
                <Th>Cake Order Status</Th>
              </Tr>
            </Thead>
            <tbody>
              {birthdays.map((item) => {
                const group = groupFor(item);
                return (
                  <Tr key={item.employee_id}>
                    <Td>
                      <p className="font-medium text-dt-text-primary">{item.display_name}</p>
                      <p className="text-xs text-dt-text-secondary">
                        {item.employee_number ?? (
                          <span className="italic text-dt-text-secondary/70">
                            {item.employee_id} (internal id — no employee #)
                          </span>
                        )}
                      </p>
                    </Td>
                    <Td>{item.birthday}</Td>
                    <Td>{item.days_until_birthday}d</Td>
                    <Td>{item.hire_date ?? "—"}</Td>
                    <Td>
                      <StatusBadge status={group} label={GROUP_LABELS[group]} />
                      {!item.eligible && (
                        <p className="mt-0.5 text-xs text-dt-text-secondary">
                          {item.eligibility_reason.replace(/_/g, " ")}
                        </p>
                      )}
                    </Td>
                    <Td>{item.location}</Td>
                    <Td>
                      {item.address_verification_status ? (
                        <StatusBadge status={item.address_verification_status} />
                      ) : (
                        <span className="text-dt-text-secondary">—</span>
                      )}
                    </Td>
                    <Td>
                      <StatusBadge status={item.cake_order_status} />
                    </Td>
                  </Tr>
                );
              })}
            </tbody>
          </Table>
          <Pagination page={data.page} pageSize={data.page_size} total={data.total} onPageChange={setPage} />
        </>
      )}
    </div>
  );
}
