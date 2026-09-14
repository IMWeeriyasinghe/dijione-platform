"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import type { ReactNode } from "react";
import { useBirthdayScope } from "@dijione/auth-client";
import {
  Button,
  EmptyState,
  ErrorState,
  FormField,
  Input,
  LoadingState,
  Modal,
  Pagination,
  PageHeader,
  SearchInput,
  Select,
  SortableTh,
  StatusBadge,
  Table,
  Td,
  Textarea,
  Th,
  Thead,
  Tr,
  useSortToggle,
  type SortDirection,
} from "@dijione/design-system";
import { createSupplier, listSuppliers } from "@/lib/api";
import type { SupplierCreateInput, SupplierOut } from "@dijione/contracts";

const PAGE_SIZE = 20;

// Round 4 — one canonical field list consumed by BOTH the table (wide
// viewports) and the card view (laptop/tablet/mobile below the measured
// breakpoint, see CARD_BREAKPOINT_CLASS below), same pattern as Upcoming
// Birthdays and Cake Orders: a label or value can never drift between the
// two views because there is exactly one render function per field.
type FieldDef = {
  key: string;
  label: string;
  sortKey?: string;
  render: (supplier: SupplierOut) => ReactNode;
};

const FIELDS: FieldDef[] = [
  {
    key: "name",
    label: "Name",
    sortKey: "name",
    render: (supplier) => <span className="font-medium text-dt-text-primary">{supplier.name}</span>,
  },
  {
    key: "status",
    label: "Status",
    sortKey: "status",
    render: (supplier) => <StatusBadge status={supplier.status} />,
  },
  {
    key: "lead_time",
    label: "Lead Time",
    sortKey: "lead_time_days",
    render: (supplier) => `${supplier.lead_time_days} days`,
  },
  { key: "working_days", label: "Working Days", render: (supplier) => supplier.working_days || "—" },
  { key: "cutoff", label: "Cutoff", render: (supplier) => supplier.cutoff_time || "—" },
  {
    key: "escalation_contact",
    label: "Escalation Contact",
    render: (supplier) => (
      <>
        {supplier.escalation_contact_name || "—"}
        {supplier.escalation_contact_email && (
          <p className="wrap-break-word text-xs text-dt-text-secondary">{supplier.escalation_contact_email}</p>
        )}
      </>
    ),
  },
];

// Below this breakpoint, the 6-column table's natural width (measured via a
// real headless-browser pass through the full AppShell — sidebar included,
// not raw viewport-width arithmetic) can't show every column without its
// own internal horizontal scroll — the card view takes over instead so no
// field ever requires an extra interaction to see. Measured: the table fits
// its available content-area width (viewport minus sidebar) with zero
// internal scroll at 1180px and above (858px content width available vs.
// 796px table content); at 1024px the same table needs 796px but only 702px
// is available, so xl (1280px) — not lg (1024px) — is the correct cutoff.
// This is the area the user explicitly flagged as having observed
// responsive problems.
const CARD_BREAKPOINT_CLASS = {
  table: "hidden xl:block",
  cards: "xl:hidden",
};

function SupplierCard({ supplier }: { supplier: SupplierOut }) {
  return (
    <Link
      href={`/suppliers/${supplier.id}`}
      className="block rounded-2xl border border-dt-border bg-dt-surface p-4 text-left transition hover:border-dt-orange focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-dt-orange focus-visible:ring-offset-1"
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">{FIELDS[0].render(supplier)}</div>
        <div className="shrink-0">{FIELDS[1].render(supplier)}</div>
      </div>
      <div className="mt-3 grid grid-cols-2 gap-x-4 gap-y-3">
        {FIELDS.slice(2).map((field) => (
          <div key={field.key} className="min-w-0">
            <p className="text-[11px] font-medium uppercase tracking-wide text-dt-text-secondary">{field.label}</p>
            <div className="mt-0.5 text-sm text-dt-text-primary">{field.render(supplier)}</div>
          </div>
        ))}
      </div>
    </Link>
  );
}

const EMPTY_FORM: SupplierCreateInput = {
  name: "",
  status: "ACTIVE",
  primary_contact_name: "",
  primary_contact_email: "",
  primary_contact_phone: "",
  escalation_contact_name: "",
  escalation_contact_email: "",
  lead_time_days: 0,
  working_days: "",
  cutoff_time: "",
  notes: "",
};

export default function SuppliersPage() {
  const scope = useBirthdayScope();
  const router = useRouter();
  const queryClient = useQueryClient();
  const [createOpen, setCreateOpen] = useState(false);
  const [form, setForm] = useState<SupplierCreateInput>(EMPTY_FORM);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [sortBy, setSortBy] = useState<string | null>(null);
  const [sortDirection, setSortDirection] = useState<SortDirection>("asc");
  const [page, setPage] = useState(1);

  const params = {
    search: search || undefined,
    status_filter: statusFilter || undefined,
    sort_by: sortBy || undefined,
    sort_direction: sortDirection,
    page,
    page_size: PAGE_SIZE,
  };

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["birthday-suppliers", params],
    queryFn: () => listSuppliers(params),
  });
  const toggleSort = useSortToggle(sortBy, sortDirection, setSortBy, setSortDirection);
  const suppliers = data?.items ?? [];

  const createMutation = useMutation({
    mutationFn: (payload: SupplierCreateInput) => createSupplier(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["birthday-suppliers"] });
      setCreateOpen(false);
      setForm(EMPTY_FORM);
    },
  });

  function updateField<K extends keyof SupplierCreateInput>(key: K, value: SupplierCreateInput[K]) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  return (
    <div>
      <PageHeader
        title="Suppliers"
        description="Cake suppliers, contacts, service locations and catalogue."
        action={
          scope?.isAdmin ? (
            <Button size="sm" onClick={() => setCreateOpen(true)}>
              <Plus className="size-4" />
              New Supplier
            </Button>
          ) : undefined
        }
      />

      <div className="mb-4 flex flex-wrap items-center gap-3">
        <SearchInput
          value={search}
          onChange={(v) => {
            setPage(1);
            setSearch(v);
          }}
          placeholder="Search supplier name or email…"
          className="max-w-md flex-1"
        />
        <Select
          value={statusFilter}
          onChange={(e) => {
            setPage(1);
            setStatusFilter(e.target.value);
          }}
          className="w-auto"
        >
          <option value="">All statuses</option>
          <option value="ACTIVE">Active</option>
          <option value="INACTIVE">Inactive</option>
        </Select>
      </div>

      {isLoading ? (
        <LoadingState label="Loading suppliers…" />
      ) : isError || !data ? (
        <ErrorState onRetry={() => refetch()} />
      ) : suppliers.length === 0 ? (
        <EmptyState title="No suppliers found" description="Add a supplier or adjust your search." />
      ) : (
        <>
          {/* Wide viewports: the full 6-column table (unchanged structurally,
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
                {suppliers.map((supplier) => {
                  const goToDetail = () => router.push(`/suppliers/${supplier.id}`);
                  return (
                    <Tr
                      key={supplier.id}
                      role="link"
                      tabIndex={0}
                      onClick={goToDetail}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          goToDetail();
                        }
                      }}
                      className="cursor-pointer hover:bg-dt-cream/40"
                    >
                      {FIELDS.map((field) => (
                        <Td key={field.key}>{field.render(supplier)}</Td>
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
                aria-label="Sort suppliers by"
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
              {suppliers.map((supplier) => (
                <SupplierCard key={supplier.id} supplier={supplier} />
              ))}
            </div>
          </div>

          <Pagination page={data.page} pageSize={data.page_size} total={data.total} onPageChange={setPage} />
        </>
      )}

      <Modal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        title="New Supplier"
      >
        <div className="flex max-h-[70vh] flex-col gap-4 overflow-y-auto pr-1">
          <FormField label="Name" htmlFor="supplier-name" required>
            <Input
              id="supplier-name"
              value={form.name}
              onChange={(e) => updateField("name", e.target.value)}
            />
          </FormField>
          <FormField label="Status" htmlFor="supplier-status">
            <Select
              id="supplier-status"
              value={form.status}
              onChange={(e) => updateField("status", e.target.value)}
            >
              <option value="ACTIVE">Active</option>
              <option value="INACTIVE">Inactive</option>
            </Select>
          </FormField>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <FormField label="Primary Contact Name" htmlFor="primary-contact-name">
              <Input
                id="primary-contact-name"
                value={form.primary_contact_name}
                onChange={(e) => updateField("primary_contact_name", e.target.value)}
              />
            </FormField>
            <FormField label="Primary Contact Email" htmlFor="primary-contact-email">
              <Input
                id="primary-contact-email"
                type="email"
                value={form.primary_contact_email}
                onChange={(e) => updateField("primary_contact_email", e.target.value)}
              />
            </FormField>
            <FormField label="Primary Contact Phone" htmlFor="primary-contact-phone">
              <Input
                id="primary-contact-phone"
                value={form.primary_contact_phone}
                onChange={(e) => updateField("primary_contact_phone", e.target.value)}
              />
            </FormField>
            <FormField label="Escalation Contact Name" htmlFor="escalation-contact-name">
              <Input
                id="escalation-contact-name"
                value={form.escalation_contact_name}
                onChange={(e) => updateField("escalation_contact_name", e.target.value)}
              />
            </FormField>
            <FormField label="Escalation Contact Email" htmlFor="escalation-contact-email">
              <Input
                id="escalation-contact-email"
                type="email"
                value={form.escalation_contact_email}
                onChange={(e) => updateField("escalation_contact_email", e.target.value)}
              />
            </FormField>
            <FormField label="Lead Time (days)" htmlFor="lead-time-days">
              <Input
                id="lead-time-days"
                type="number"
                min={0}
                value={form.lead_time_days}
                onChange={(e) => updateField("lead_time_days", Number(e.target.value))}
              />
            </FormField>
            <FormField label="Working Days" htmlFor="working-days" hint="e.g. Mon-Fri">
              <Input
                id="working-days"
                value={form.working_days}
                onChange={(e) => updateField("working_days", e.target.value)}
              />
            </FormField>
            <FormField label="Cutoff Time" htmlFor="cutoff-time" hint="e.g. 14:00">
              <Input
                id="cutoff-time"
                value={form.cutoff_time}
                onChange={(e) => updateField("cutoff_time", e.target.value)}
              />
            </FormField>
          </div>
          <FormField label="Notes" htmlFor="supplier-notes" hint="Internal-only, never shared with the supplier.">
            <Textarea
              id="supplier-notes"
              value={form.notes}
              onChange={(e) => updateField("notes", e.target.value)}
            />
          </FormField>
          <div className="flex justify-end gap-2">
            <Button variant="secondary" size="sm" onClick={() => setCreateOpen(false)}>
              Cancel
            </Button>
            <Button
              size="sm"
              loading={createMutation.isPending}
              disabled={form.name.trim() === ""}
              onClick={() => createMutation.mutate(form)}
            >
              Create Supplier
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
