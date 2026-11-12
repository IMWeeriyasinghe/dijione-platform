"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import type { ReactNode } from "react";
import { useBirthdayScope } from "@dijione/auth-client";
import {
  getPeopleFreshness,
  getUpcomingBirthdays,
  refreshPeople,
  runBirthdayDetection,
  type RunDetectionResult,
} from "@/lib/api";
import { ORDER_STATUSES, type UpcomingBirthdayItem } from "@dijione/contracts";
import {
  Button,
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

// Provinces observed live for this tenant's Sri Lanka roster (see
// docs/platform/bamboohr-live-discovery.md, 2026-08-15 discovery) — a
// fixed list keeps the filter a simple dropdown rather than a free-text
// field with inconsistent casing/spelling.
const PROVINCE_OPTIONS = [
  "Western",
  "Southern",
  "Central",
  "North Western",
  "Sabaragamuwa",
  "Uva",
  "North Central",
  "Northern",
  "Eastern",
];

// Any ineligible reason other than FUTURE_STARTER (INACTIVE_EMPLOYEE,
// EMPLOYMENT_ENDED, MISSING_HIRE_DATE, MISSING_BIRTHDAY,
// INVALID_EMPLOYEE_DATA) falls into the "Not Eligible" group by default in
// groupFor() below — no explicit list needed here.
const NEEDS_ATTENTION_ORDER_STATUSES = new Set(["REQUIRES_ATTENTION", "REQUIRES_REVIEW", "ON_HOLD"]);
const NEEDS_ATTENTION_ADDRESS_STATUSES = new Set(["NEEDS_UPDATE", "VERIFICATION_REQUESTED"]);

type Group = "ELIGIBLE" | "FUTURE_STARTER" | "NOT_ELIGIBLE" | "NEEDS_ATTENTION";

// Phase 1.6 §16 (R15) — the curated default: "who has a birthday coming up
// that I actually need to look at", not every group mixed together. The
// backend's group_filter now accepts a comma-list (mirroring
// cake_status_filter's existing pattern) specifically to support this.
// "ALL" stays one click away in the same Select.
const DEFAULT_GROUP_FILTER = "ELIGIBLE,NEEDS_ATTENTION";

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

// Responsive review round 3 — one canonical field list consumed by BOTH the
// table (wide viewports) and the card view (laptop/tablet/mobile below the
// measured breakpoint, see BREAKPOINT below). A label or a value can never
// drift between the two views because there is exactly one render function
// per field, not two hand-maintained copies.
type FieldDef = {
  key: string;
  label: string;
  /** Present only for the 7 fields the backend can sort by today — Eligibility
   * and Address Verification have no server sort, unchanged from before this
   * round. */
  sortKey?: string;
  render: (item: UpcomingBirthdayItem, group: Group) => ReactNode;
};

const FIELDS: FieldDef[] = [
  {
    key: "team_member",
    label: "Team Member",
    sortKey: "employee_number",
    render: (item) => (
      <>
        <span className="font-medium text-dt-text-primary">{item.display_name}</span>{" "}
        {item.employee_number ? (
          <span className="whitespace-nowrap font-mono text-xs text-dt-text-secondary">
            ({item.employee_number})
          </span>
        ) : (
          <span className="whitespace-nowrap text-xs italic text-dt-text-secondary/70">(no Team Member ID)</span>
        )}
      </>
    ),
  },
  { key: "birthday", label: "Birthday", sortKey: "birthday", render: (item) => item.birthday },
  {
    key: "days_until",
    label: "Days Until",
    sortKey: "days_until_birthday",
    render: (item) => `${item.days_until_birthday}d`,
  },
  { key: "hire_date", label: "Hire Date", sortKey: "hire_date", render: (item) => item.hire_date ?? "—" },
  {
    key: "eligibility",
    label: "Eligibility",
    render: (item, group) => (
      <>
        <StatusBadge status={group} label={GROUP_LABELS[group]} />
        {!item.eligible && (
          <p className="mt-0.5 text-xs text-dt-text-secondary">{item.eligibility_reason.replace(/_/g, " ")}</p>
        )}
      </>
    ),
  },
  { key: "location", label: "Location", sortKey: "city", render: (item) => item.city ?? "—" },
  {
    key: "address_verification",
    label: "Address Verification",
    render: (item) =>
      item.order_id == null ? (
        <span className="text-dt-text-secondary">No order yet</span>
      ) : item.address_verification_status ? (
        <StatusBadge status={item.address_verification_status} />
      ) : (
        <span className="text-dt-text-secondary">—</span>
      ),
  },
  {
    key: "cake_order_status",
    label: "Cake Order Status",
    sortKey: "cake_order_status",
    render: (item) => <StatusBadge status={item.cake_order_status} />,
  },
  {
    key: "order_reference",
    label: "Order Reference",
    render: (item) =>
      item.order_id != null && item.order_reference ? (
        <span className="font-mono text-xs text-dt-burnt-orange">{item.order_reference}</span>
      ) : (
        <span className="text-dt-text-secondary">No order yet</span>
      ),
  },
];

// Below this breakpoint, the 9-column table's natural width (measured via a
// real headless-browser pass, not guessed) can't show every column without
// its own internal horizontal scroll — the card view takes over instead so
// no field ever requires an extra interaction to see.
const CARD_BREAKPOINT_CLASS = {
  table: "hidden xl:block",
  cards: "xl:hidden",
};

function UpcomingCard({ item, group }: { item: UpcomingBirthdayItem; group: Group }) {
  const clickable = item.order_id != null;
  const cardClassName =
    "block rounded-2xl border border-dt-border bg-dt-surface p-4 text-left transition hover:border-dt-orange focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-dt-orange focus-visible:ring-offset-1";

  const body = (
    <>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">{FIELDS[0].render(item, group)}</div>
      </div>
      <div className="mt-3 grid grid-cols-2 gap-x-4 gap-y-3">
        {FIELDS.slice(1).map((field) => (
          <div key={field.key} className="min-w-0">
            <p className="text-[11px] font-medium uppercase tracking-wide text-dt-text-secondary">{field.label}</p>
            <div className="mt-0.5 text-sm text-dt-text-primary">{field.render(item, group)}</div>
          </div>
        ))}
      </div>
    </>
  );

  // A real <a> (via next/link) when the card is actually navigable — native
  // keyboard focus + Enter activation, no manual role/tabIndex/onKeyDown
  // needed. Only falls back to a plain, inert (non-interactive, no click
  // handler, no focus ring implied) <div> for the genuinely non-clickable
  // case (no order created yet for this person) — never a clickable div.
  if (clickable) {
    return (
      <Link href={`/orders/${item.order_id}`} className={cardClassName}>
        {body}
      </Link>
    );
  }
  return <div className={`${cardClassName} cursor-default hover:border-dt-border`}>{body}</div>;
}

// Sourced live from BambooHR (active employees only, filtered server-side
// in birthday-api) — not from BirthdayOrder rows, so an employee shows up
// here even before the daily detection scan has created a cake order for
// them. Eligibility, search, group filtering, sorting and pagination are
// all computed/applied server-side (Phase-Next §4) — this page only
// renders the result.
export default function UpcomingPage() {
  const scope = useBirthdayScope();
  const router = useRouter();
  const qc = useQueryClient();
  const [days, setDays] = useState(30);
  // string, not Group | "ALL": a comma-list is a real supported value now
  // (Phase 1.6 §16) — "ALL" (empty filter) stays available in the Select.
  const [groupFilter, setGroupFilter] = useState<string>(DEFAULT_GROUP_FILTER);
  const [cakeStatusFilter, setCakeStatusFilter] = useState("");
  const [province, setProvince] = useState("");
  const [search, setSearch] = useState("");
  // Explicit default (Phase 1.6 §16/R15) — the server already falls back to
  // this when sort_by is empty, but asserting it here means the default
  // ordering is declared where a future change is most likely to be made,
  // not left to an implicit backend fallback.
  const [sortBy, setSortBy] = useState<string | null>("days_until_birthday");
  const [sortDirection, setSortDirection] = useState<SortDirection>("asc");
  const [page, setPage] = useState(1);
  const [scanResult, setScanResult] = useState<RunDetectionResult | null>(null);

  const params = {
    days,
    search: search || undefined,
    filter: groupFilter !== "ALL" ? groupFilter : undefined,
    cake_status_filter: cakeStatusFilter || undefined,
    province: province || undefined,
    sort_by: sortBy || undefined,
    sort_direction: sortDirection,
    page,
    page_size: PAGE_SIZE,
  };

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["birthday-upcoming-birthdays", params],
    queryFn: () => getUpcomingBirthdays(params),
  });

  const { data: freshness } = useQuery({
    queryKey: ["people-freshness"],
    queryFn: getPeopleFreshness,
  });

  const refreshMutation = useMutation({
    mutationFn: () => refreshPeople(),
    onSuccess: () => {
      // People sync runs async; re-poll freshness shortly.
      setTimeout(() => qc.invalidateQueries({ queryKey: ["people-freshness"] }), 4000);
    },
  });

  const runDetectionMutation = useMutation({
    mutationFn: () => runBirthdayDetection(),
    onSuccess: (result) => {
      setScanResult(result);
      refetch();
    },
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
        description="Active team members with birthdays approaching, sourced from BambooHR, with eligibility and address-verification status for each cake order."
        actionLayout="stacked"
        action={
          <div className="flex flex-wrap gap-2">
            <Select
              value={groupFilter}
              onChange={(e) => resetAndSet(setGroupFilter, e.target.value)}
              className="w-auto"
            >
              <option value={DEFAULT_GROUP_FILTER}>Needs my attention (default)</option>
              <option value="ALL">All groups</option>
              {GROUP_FILTER_OPTIONS.filter((g) => g !== "ALL").map((g) => (
                <option key={g} value={g}>
                  {GROUP_LABELS[g as Group]}
                </option>
              ))}
            </Select>
            <Select
              value={cakeStatusFilter}
              onChange={(e) => resetAndSet(setCakeStatusFilter, e.target.value)}
              className="w-auto"
            >
              <option value="">All cake order statuses</option>
              <option value="NOT_CREATED">No order yet</option>
              {ORDER_STATUSES.map((s) => (
                <option key={s} value={s}>
                  {s.replace(/_/g, " ")}
                </option>
              ))}
            </Select>
            <Select value={province} onChange={(e) => resetAndSet(setProvince, e.target.value)} className="w-auto">
              <option value="">All provinces</option>
              {PROVINCE_OPTIONS.map((p) => (
                <option key={p} value={p}>
                  {p}
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
            {scope?.isAdmin && (
              <Button
                size="sm"
                variant="secondary"
                loading={runDetectionMutation.isPending}
                onClick={() => runDetectionMutation.mutate()}
                title="Re-scans the current team-member data for new/changed birthdays and creates cake orders."
              >
                Run Detection
              </Button>
            )}
          </div>
        }
      />

      {/* Team-member data freshness (Phase 1.5 §B). Detection ≠ refresh:
          refresh pulls BambooHR; detection creates cake orders from it. */}
      <div className="mb-4 flex flex-wrap items-center gap-3 rounded-xl border border-dt-border bg-dt-surface-warm/50 px-3 py-2 text-sm">
        <span className="text-dt-text-secondary">
          Team-member data auto-refreshes from BambooHR every day (~midnight).
          {freshness?.last_successful_sync_at ? (
            <> Last refreshed <span className="text-dt-text-primary">{new Date(freshness.last_successful_sync_at).toLocaleString()}</span>.</>
          ) : freshness?.available === false ? (
            <> ({freshness.reason ?? "freshness unavailable"})</>
          ) : (
            <> Loading…</>
          )}
        </span>
        {scope?.isAdmin && freshness?.available !== false && (
          <Button
            size="sm"
            variant="secondary"
            loading={refreshMutation.isPending}
            onClick={() => refreshMutation.mutate()}
          >
            Refresh now
          </Button>
        )}
        {refreshMutation.isSuccess && (
          <span className="text-xs text-dt-success">Refresh started — this updates in a moment.</span>
        )}
      </div>

      {scanResult && (
        <div className="mb-4 rounded-xl border border-dt-border bg-dt-surface-warm/60 p-3 text-sm text-dt-text-primary">
          <p className="font-medium">
            Scan complete — scanned {scanResult.employees_scanned}, created {scanResult.orders_created}, already
            existed {scanResult.orders_existing}, skipped/ineligible {scanResult.ineligible_skipped}, exceptions{" "}
            {scanResult.exceptions}
            {scanResult.errors.length > 0 && `, failed ${scanResult.errors.length}`}.
          </p>
          {scanResult.errors.length > 0 && (
            <ul className="mt-1 list-disc pl-5 text-xs text-dt-text-secondary">
              {scanResult.errors.map((err, i) => (
                <li key={i}>
                  {err.employee_id ?? "unknown"}: {err.error}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      <SearchInput
        value={search}
        onChange={(v) => resetAndSet(setSearch, v)}
        placeholder="Search name, team member ID, city, or order reference…"
        className="mb-4 max-w-md"
      />

      {isLoading ? (
        <LoadingState label="Loading upcoming birthdays…" />
      ) : isError || !data ? (
        <ErrorState onRetry={() => refetch()} />
      ) : birthdays.length === 0 ? (
        <EmptyState
          title="No matches"
          description={`No team members found within the next ${days} days for the current search/filter.`}
        />
      ) : (
        <>
          {/* Wide viewports: the full 9-column table (unchanged structurally,
              now sourced from the shared FIELDS list). */}
          <div className={CARD_BREAKPOINT_CLASS.table}>
            <Table>
              <Thead>
                <Tr>
                  {FIELDS.map((field) =>
                    field.sortKey ? (
                      <SortableTh
                        key={field.key}
                        label={field.label}
                        sortKey={field.sortKey}
                        activeSortBy={sortBy}
                        sortDirection={sortDirection}
                        onSort={toggleSort}
                      />
                    ) : (
                      <Th key={field.key}>{field.label}</Th>
                    )
                  )}
                </Tr>
              </Thead>
              <tbody>
                {birthdays.map((item) => {
                  const group = groupFor(item);
                  const clickable = item.order_id != null;
                  return (
                    <Tr
                      key={item.employee_id}
                      className={clickable ? "cursor-pointer transition hover:bg-dt-surface-warm" : undefined}
                      onClick={clickable ? () => router.push(`/orders/${item.order_id}`) : undefined}
                    >
                      {FIELDS.map((field) => (
                        <Td key={field.key}>{field.render(item, group)}</Td>
                      ))}
                    </Tr>
                  );
                })}
              </tbody>
            </Table>
          </div>

          {/* Laptop/tablet/mobile: cards, same FIELDS, no field ever hidden
              behind an extra interaction. */}
          <div className={CARD_BREAKPOINT_CLASS.cards}>
            <div className="mb-4 flex flex-wrap items-center gap-2">
              <span className="text-xs font-medium uppercase tracking-wide text-dt-text-secondary">Sort by</span>
              <Select
                value={sortBy ?? ""}
                onChange={(e) => toggleSort(e.target.value)}
                className="w-auto"
                aria-label="Sort upcoming birthdays by"
              >
                {FIELDS.filter((f) => f.sortKey).map((f) => (
                  <option key={f.sortKey} value={f.sortKey}>
                    {f.label}
                  </option>
                ))}
              </Select>
              <Button
                size="sm"
                variant="secondary"
                onClick={() => setSortDirection((d) => (d === "asc" ? "desc" : "asc"))}
                title={sortDirection === "asc" ? "Ascending — click for descending" : "Descending — click for ascending"}
              >
                {sortDirection === "asc" ? "↑ Ascending" : "↓ Descending"}
              </Button>
            </div>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              {birthdays.map((item) => {
                const group = groupFor(item);
                return <UpcomingCard key={item.employee_id} item={item} group={group} />;
              })}
            </div>
          </div>

          <Pagination page={data.page} pageSize={data.page_size} total={data.total} onPageChange={setPage} />
        </>
      )}
    </div>
  );
}
