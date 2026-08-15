"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
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
import type { SupplierCreateInput } from "@dijione/contracts";

const PAGE_SIZE = 20;

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
          <Table>
            <Thead>
              <Tr>
                <SortableTh label="Name" sortKey="name" activeSortBy={sortBy} sortDirection={sortDirection} onSort={toggleSort} />
                <SortableTh label="Status" sortKey="status" activeSortBy={sortBy} sortDirection={sortDirection} onSort={toggleSort} />
                <SortableTh
                  label="Lead Time"
                  sortKey="lead_time_days"
                  activeSortBy={sortBy}
                  sortDirection={sortDirection}
                  onSort={toggleSort}
                />
                <Th>Working Days</Th>
                <Th>Cutoff</Th>
                <Th>Escalation Contact</Th>
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
                    <Td>
                      <span className="font-medium text-dt-text-primary">{supplier.name}</span>
                    </Td>
                    <Td>
                      <StatusBadge status={supplier.status} />
                    </Td>
                    <Td>{supplier.lead_time_days} days</Td>
                    <Td>{supplier.working_days || "—"}</Td>
                    <Td>{supplier.cutoff_time || "—"}</Td>
                    <Td>
                      {supplier.escalation_contact_name || "—"}
                      {supplier.escalation_contact_email && (
                        <p className="text-xs text-dt-text-secondary">{supplier.escalation_contact_email}</p>
                      )}
                    </Td>
                  </Tr>
                );
              })}
            </tbody>
          </Table>
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
