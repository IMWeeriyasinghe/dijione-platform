"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Ban, CheckCircle2, Plus } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { useBirthdayScope } from "@dijione/auth-client";
import {
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  ErrorState,
  FormField,
  Input,
  LoadingState,
  Modal,
  Select,
  StatusBadge,
  Textarea,
} from "@dijione/design-system";
import {
  addSupplierCatalogueItem,
  addSupplierLocation,
  createSupplierUser,
  getSupplier,
  getSupplierReadiness,
  impersonateSupplierUser,
  listSupplierCatalogue,
  listSupplierLocations,
  listSupplierUsers,
  markSupplierUserInvited,
  updateSupplier,
  updateSupplierCatalogueItem,
  updateSupplierUser,
} from "@/lib/api";
import type {
  SupplierCatalogueItemOut,
  SupplierUpdateInput,
  SupplierUserCreateInput,
  SupplierUserOut,
} from "@dijione/contracts";

type SupplierUserForm = SupplierUserCreateInput & { entra_object_id?: string };

const EMPTY_USER_FORM: SupplierUserForm = {
  email: "",
  full_name: "",
  role: "SUPPLIER_USER",
  status: "ACTIVE",
  entra_object_id: "",
};

function DetailRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-xs font-medium uppercase tracking-wide text-dt-text-secondary">{label}</span>
      <span className="text-sm text-dt-text-primary">{value}</span>
    </div>
  );
}

export function SupplierDetail({ supplierId }: { supplierId: number }) {
  const scope = useBirthdayScope();
  const queryClient = useQueryClient();

  const {
    data: supplier,
    isLoading,
    isError,
    refetch,
  } = useQuery({ queryKey: ["birthday-supplier", supplierId], queryFn: () => getSupplier(supplierId) });

  const { data: readiness } = useQuery({
    queryKey: ["birthday-supplier-readiness", supplierId],
    queryFn: () => getSupplierReadiness(supplierId),
  });

  const markInvited = useMutation({
    mutationFn: (userId: number) => markSupplierUserInvited(supplierId, userId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["birthday-supplier-users", supplierId] }),
  });

  // §C — open the real portal in a new tab as this user, read-only. POST
  // the token via an auto-submitting form so the bearer never hits history.
  const impersonate = useMutation({
    mutationFn: (userId: number) => impersonateSupplierUser(supplierId, userId),
    onSuccess: ({ access_token, portal_url }) => {
      if (!portal_url) {
        window.alert("Supplier portal URL is not configured for this environment.");
        return;
      }
      const form = document.createElement("form");
      form.method = "POST";
      form.action = `${portal_url.replace(/\/$/, "")}/impersonate`;
      form.target = "_blank";
      const input = document.createElement("input");
      input.type = "hidden";
      input.name = "token";
      input.value = access_token;
      form.appendChild(input);
      document.body.appendChild(form);
      form.submit();
      form.remove();
    },
  });

  const { data: locations, refetch: refetchLocations } = useQuery({
    queryKey: ["birthday-supplier-locations", supplierId],
    queryFn: () => listSupplierLocations(supplierId),
  });

  const { data: catalogue, refetch: refetchCatalogue } = useQuery({
    queryKey: ["birthday-supplier-catalogue", supplierId],
    queryFn: () => listSupplierCatalogue(supplierId),
  });

  const { data: supplierUsers, refetch: refetchUsers } = useQuery({
    queryKey: ["birthday-supplier-users", supplierId],
    queryFn: () => listSupplierUsers(supplierId),
  });

  const [editForm, setEditForm] = useState<SupplierUpdateInput | null>(null);
  const [editOpen, setEditOpen] = useState(false);
  const [locationOpen, setLocationOpen] = useState(false);
  const [newLocation, setNewLocation] = useState({ office_location: "", is_primary: false });
  const [catalogueOpen, setCatalogueOpen] = useState(false);
  const [editingItem, setEditingItem] = useState<SupplierCatalogueItemOut | null>(null);
  const [catalogueForm, setCatalogueForm] = useState({ name: "", description: "", is_active: true });
  const [userModalOpen, setUserModalOpen] = useState(false);
  const [editingUser, setEditingUser] = useState<SupplierUserOut | null>(null);
  const [userForm, setUserForm] = useState<SupplierUserForm>(EMPTY_USER_FORM);

  function openEdit() {
    if (!supplier) return;
    setEditForm({
      name: supplier.name,
      status: supplier.status,
      primary_contact_name: supplier.primary_contact_name,
      primary_contact_email: supplier.primary_contact_email,
      primary_contact_phone: supplier.primary_contact_phone,
      escalation_contact_name: supplier.escalation_contact_name,
      escalation_contact_email: supplier.escalation_contact_email,
      lead_time_days: supplier.lead_time_days,
      working_days: supplier.working_days,
      cutoff_time: supplier.cutoff_time,
      notes: supplier.notes,
      is_default: supplier.is_default,
    });
    setEditOpen(true);
  }

  const updateMutation = useMutation({
    mutationFn: (payload: SupplierUpdateInput) => updateSupplier(supplierId, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["birthday-supplier", supplierId] });
      queryClient.invalidateQueries({ queryKey: ["birthday-suppliers"] });
      setEditOpen(false);
    },
  });

  const addLocationMutation = useMutation({
    mutationFn: () => addSupplierLocation(supplierId, newLocation),
    onSuccess: () => {
      refetchLocations();
      queryClient.invalidateQueries({ queryKey: ["birthday-supplier-readiness", supplierId] });
      setLocationOpen(false);
      setNewLocation({ office_location: "", is_primary: false });
    },
  });

  const catalogueMutation = useMutation({
    mutationFn: () =>
      editingItem
        ? updateSupplierCatalogueItem(supplierId, editingItem.id, catalogueForm)
        : addSupplierCatalogueItem(supplierId, catalogueForm),
    onSuccess: () => {
      refetchCatalogue();
      queryClient.invalidateQueries({ queryKey: ["birthday-supplier-readiness", supplierId] });
      setCatalogueOpen(false);
      setEditingItem(null);
      setCatalogueForm({ name: "", description: "", is_active: true });
    },
  });

  const statusToggleMutation = useMutation({
    mutationFn: (nextStatus: string) => updateSupplier(supplierId, { status: nextStatus }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["birthday-supplier", supplierId] });
      queryClient.invalidateQueries({ queryKey: ["birthday-suppliers"] });
    },
  });

  const userMutation = useMutation({
    mutationFn: () => {
      const { entra_object_id, ...base } = userForm;
      return editingUser
        ? updateSupplierUser(supplierId, editingUser.id, {
            ...base,
            // Only send the link when the admin actually changed it, and
            // send null (not "") to clear it.
            ...(entra_object_id !== (editingUser.entra_object_id ?? "")
              ? { entra_object_id: entra_object_id?.trim() ? entra_object_id.trim() : null }
              : {}),
          })
        : createSupplierUser(supplierId, base);
    },
    onSuccess: () => {
      refetchUsers();
      queryClient.invalidateQueries({ queryKey: ["birthday-supplier-readiness", supplierId] });
      setUserModalOpen(false);
      setEditingUser(null);
      setUserForm(EMPTY_USER_FORM);
    },
  });

  const userStatusToggleMutation = useMutation({
    mutationFn: ({ user, nextStatus }: { user: SupplierUserOut; nextStatus: string }) =>
      updateSupplierUser(supplierId, user.id, { status: nextStatus }),
    onSuccess: () => {
      refetchUsers();
      queryClient.invalidateQueries({ queryKey: ["birthday-supplier-readiness", supplierId] });
    },
  });

  function openUserCreate() {
    setEditingUser(null);
    setUserForm(EMPTY_USER_FORM);
    setUserModalOpen(true);
  }

  function openUserEdit(user: SupplierUserOut) {
    setEditingUser(user);
    setUserForm({
      email: user.email,
      full_name: user.full_name,
      role: user.role,
      status: user.status,
      entra_object_id: user.entra_object_id ?? "",
    });
    setUserModalOpen(true);
  }

  if (isLoading) return <LoadingState label="Loading supplier…" />;
  if (isError || !supplier) return <ErrorState onRetry={() => refetch()} />;

  function openCatalogueCreate() {
    setEditingItem(null);
    setCatalogueForm({ name: "", description: "", is_active: true });
    setCatalogueOpen(true);
  }

  function openCatalogueEdit(item: SupplierCatalogueItemOut) {
    setEditingItem(item);
    setCatalogueForm({ name: item.name, description: item.description, is_active: item.is_active });
    setCatalogueOpen(true);
  }

  return (
    <div>
      <Link
        href="/suppliers"
        className="mb-4 inline-flex items-center gap-1.5 text-sm text-dt-text-secondary hover:text-dt-text-primary"
      >
        <ArrowLeft className="size-4" />
        Back to suppliers
      </Link>

      {/* Round 4 — hardened to the same 2xl stacked pattern as OrderDetail.tsx's
          header (defense-in-depth: a long supplier name + 2 admin buttons
          could pinch under the older sm:flex-row default, even though no
          concrete overflow was measured at the time this was written). */}
      <div className="mb-6 flex flex-col gap-4 rounded-2xl border border-dt-border bg-dt-surface p-5 2xl:flex-row 2xl:flex-wrap 2xl:items-start 2xl:justify-between">
        <div className="min-w-0 max-w-full">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="wrap-break-word text-xl font-semibold text-dt-text-primary">{supplier.name}</h1>
            <StatusBadge status={supplier.status} />
            {supplier.is_default && <StatusBadge status="INFO" label="Island-wide default" />}
          </div>
          <p className="mt-1 wrap-break-word text-sm text-dt-text-secondary">
            {supplier.primary_contact_name || "No primary contact"} ·{" "}
            {supplier.primary_contact_email || "—"}
          </p>
        </div>

        {scope?.isAdmin && (
          <div className="flex w-full flex-wrap gap-2 2xl:w-auto 2xl:shrink-0">
            <Button size="sm" variant="secondary" onClick={openEdit}>
              Edit Supplier
            </Button>
            <Button
              size="sm"
              variant={supplier.status === "ACTIVE" ? "danger" : "primary"}
              loading={statusToggleMutation.isPending}
              onClick={() =>
                statusToggleMutation.mutate(supplier.status === "ACTIVE" ? "INACTIVE" : "ACTIVE")
              }
            >
              {supplier.status === "ACTIVE" ? (
                <>
                  <Ban className="size-4" />
                  Deactivate
                </>
              ) : (
                <>
                  <CheckCircle2 className="size-4" />
                  Activate
                </>
              )}
            </Button>
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="flex flex-col gap-6 lg:col-span-2">
          <Card>
            <CardHeader>
              <CardTitle>Supplier Details</CardTitle>
            </CardHeader>
            <CardContent className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <DetailRow label="Lead Time" value={`${supplier.lead_time_days} days`} />
              <DetailRow label="Working Days" value={supplier.working_days || "—"} />
              <DetailRow label="Cutoff Time" value={supplier.cutoff_time || "—"} />
              <DetailRow label="Primary Contact Phone" value={supplier.primary_contact_phone || "—"} />
              <DetailRow label="Escalation Contact" value={supplier.escalation_contact_name || "—"} />
              <DetailRow label="Escalation Email" value={supplier.escalation_contact_email || "—"} />
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <CardTitle>Locations Served</CardTitle>
              {scope?.isAdmin && (
                <Button size="sm" variant="secondary" onClick={() => setLocationOpen(true)}>
                  <Plus className="size-4" />
                  Add Location
                </Button>
              )}
            </CardHeader>
            <CardContent>
              {!locations || locations.length === 0 ? (
                <p className="text-sm text-dt-text-secondary">No locations recorded.</p>
              ) : (
                <ul className="flex flex-col gap-2">
                  {locations.map((loc) => (
                    <li
                      key={loc.id}
                      className="flex items-center justify-between gap-3 rounded-xl border border-dt-border p-3"
                    >
                      <span className="min-w-0 wrap-break-word text-sm text-dt-text-primary">{loc.office_location}</span>
                      {loc.is_primary && (
                        <span className="shrink-0">
                          <StatusBadge status="PRIMARY" label="Primary" />
                        </span>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <CardTitle>Catalogue</CardTitle>
              {scope?.isAdmin && (
                <Button size="sm" variant="secondary" onClick={openCatalogueCreate}>
                  <Plus className="size-4" />
                  Add Item
                </Button>
              )}
            </CardHeader>
            <CardContent>
              {!catalogue || catalogue.length === 0 ? (
                <p className="text-sm text-dt-text-secondary">No catalogue items recorded.</p>
              ) : (
                <ul className="flex flex-col gap-2">
                  {catalogue.map((item) => (
                    <li
                      key={item.id}
                      className="flex items-center justify-between gap-3 rounded-xl border border-dt-border p-3"
                    >
                      <div className="min-w-0">
                        <p className="text-sm font-medium text-dt-text-primary">{item.name}</p>
                        {item.description && (
                          <p className="text-xs text-dt-text-secondary">{item.description}</p>
                        )}
                      </div>
                      <div className="flex shrink-0 items-center gap-2">
                        <StatusBadge status={item.is_active ? "ACTIVE" : "INACTIVE"} />
                        {scope?.isAdmin && (
                          <Button size="sm" variant="secondary" onClick={() => openCatalogueEdit(item)}>
                            Edit
                          </Button>
                        )}
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>

          {readiness && !readiness.ready && (
            <Card>
              <CardHeader>
                <CardTitle>Setup readiness</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="mb-2 text-sm text-dt-text-secondary">
                  This supplier is not fully set up — detection may route orders here that then land in
                  Requires Attention:
                </p>
                <ul className="list-disc pl-5 text-sm text-dt-danger">
                  {readiness.missing.map((m) => (
                    <li key={m}>{m}</li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          )}

          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <CardTitle>Supplier Users</CardTitle>
              {scope?.isAdmin && (
                <Button size="sm" variant="secondary" onClick={openUserCreate}>
                  <Plus className="size-4" />
                  Add Supplier User
                </Button>
              )}
            </CardHeader>
            <CardContent>
              <p className="mb-3 text-sm text-dt-text-secondary">
                Accounts that can sign in to the supplier portal. Production sign-in uses Microsoft
                Entra ID B2B guest; deactivating a user here revokes portal access immediately.
              </p>
              {!supplierUsers || supplierUsers.length === 0 ? (
                <p className="text-sm text-dt-text-secondary">No supplier users found.</p>
              ) : (
                <ul className="flex flex-col gap-2">
                  {supplierUsers.map((user) => (
                    // Round 4 — restructured into two stacked sub-rows below
                    // sm: (identity text, then the control cluster on its own
                    // line) instead of relying on flex-wrap's default
                    // left-to-right reflow, which used to interleave text and
                    // up to 5 controls unpredictably on narrow viewports.
                    <li
                      key={user.id}
                      className="flex flex-col gap-3 rounded-xl border border-dt-border p-3 sm:flex-row sm:items-center sm:justify-between"
                    >
                      <div className="min-w-0">
                        <p className="wrap-break-word text-sm font-medium text-dt-text-primary">
                          {user.full_name || user.email}
                        </p>
                        <p className="wrap-break-word text-xs text-dt-text-secondary">
                          {user.email} · {user.role.replace(/_/g, " ")}
                          {user.last_login_at &&
                            ` · last sign-in ${new Date(user.last_login_at).toLocaleDateString()}`}
                        </p>
                      </div>
                      <div className="flex flex-wrap items-center gap-2 sm:shrink-0">
                        <span className="rounded-full bg-dt-surface-warm px-2 py-0.5 text-[11px] font-medium text-dt-text-secondary">
                          {user.onboarding_state.replace(/_/g, " ")}
                        </span>
                        {scope?.isAdmin && user.onboarding_state === "NOT_INVITED" && (
                          <Button
                            size="sm"
                            variant="secondary"
                            onClick={() => markInvited.mutate(user.id)}
                          >
                            Mark invited
                          </Button>
                        )}
                        <StatusBadge status={user.status} />
                        {scope?.isAdmin && (
                          <>
                            {user.status === "ACTIVE" && (
                              <Button
                                size="sm"
                                variant="secondary"
                                loading={impersonate.isPending && impersonate.variables === user.id}
                                onClick={() => impersonate.mutate(user.id)}
                                title="Open the supplier portal in a new tab as this user — read-only preview."
                              >
                                View portal as
                              </Button>
                            )}
                            <Button size="sm" variant="secondary" onClick={() => openUserEdit(user)}>
                              Edit
                            </Button>
                            <Button
                              size="sm"
                              variant={user.status === "ACTIVE" ? "danger" : "primary"}
                              loading={
                                userStatusToggleMutation.isPending &&
                                userStatusToggleMutation.variables?.user.id === user.id
                              }
                              onClick={() =>
                                userStatusToggleMutation.mutate({
                                  user,
                                  nextStatus: user.status === "ACTIVE" ? "INACTIVE" : "ACTIVE",
                                })
                              }
                            >
                              {user.status === "ACTIVE" ? "Deactivate" : "Activate"}
                            </Button>
                          </>
                        )}
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Phase 1.6 §13 (R21) — kept (confirmed already correctly isolated
            from every supplier-facing schema/response), collapsed by
            default when empty so an empty card doesn't take a full block;
            opens automatically once a note exists. */}
        <details open={Boolean(supplier.notes)} className="rounded-2xl border border-dt-border bg-dt-surface">
          <summary className="cursor-pointer px-5 py-3 text-sm font-medium text-dt-text-primary">
            Internal Notes
          </summary>
          <div className="px-5 pb-4">
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-dt-warning">
              Internal only — never shared with the supplier
            </p>
            <p className="whitespace-pre-wrap text-sm text-dt-text-primary">
              {supplier.notes || "No notes recorded."}
            </p>
          </div>
        </details>
      </div>

      <Modal open={editOpen && editForm !== null} onClose={() => setEditOpen(false)} title="Edit Supplier">
        {editForm && (
        <div className="flex max-h-[70vh] flex-col gap-4 overflow-y-auto pr-1">
          <FormField label="Name" htmlFor="edit-name" required>
            <Input
              id="edit-name"
              value={editForm.name}
              onChange={(e) => setEditForm((f) => f && { ...f, name: e.target.value })}
            />
          </FormField>
          <FormField label="Status" htmlFor="edit-status">
            <Select
              id="edit-status"
              value={editForm.status}
              onChange={(e) => setEditForm((f) => f && { ...f, status: e.target.value })}
            >
              <option value="ACTIVE">Active</option>
              <option value="INACTIVE">Inactive</option>
            </Select>
          </FormField>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <FormField label="Primary Contact Name" htmlFor="edit-primary-name">
              <Input
                id="edit-primary-name"
                value={editForm.primary_contact_name}
                onChange={(e) => setEditForm((f) => f && { ...f, primary_contact_name: e.target.value })}
              />
            </FormField>
            <FormField label="Primary Contact Email" htmlFor="edit-primary-email">
              <Input
                id="edit-primary-email"
                type="email"
                value={editForm.primary_contact_email}
                onChange={(e) => setEditForm((f) => f && { ...f, primary_contact_email: e.target.value })}
              />
            </FormField>
            <FormField label="Primary Contact Phone" htmlFor="edit-primary-phone">
              <Input
                id="edit-primary-phone"
                value={editForm.primary_contact_phone}
                onChange={(e) => setEditForm((f) => f && { ...f, primary_contact_phone: e.target.value })}
              />
            </FormField>
            <FormField label="Escalation Contact Name" htmlFor="edit-escalation-name">
              <Input
                id="edit-escalation-name"
                value={editForm.escalation_contact_name}
                onChange={(e) => setEditForm((f) => f && { ...f, escalation_contact_name: e.target.value })}
              />
            </FormField>
            <FormField label="Escalation Contact Email" htmlFor="edit-escalation-email">
              <Input
                id="edit-escalation-email"
                type="email"
                value={editForm.escalation_contact_email}
                onChange={(e) => setEditForm((f) => f && { ...f, escalation_contact_email: e.target.value })}
              />
            </FormField>
            <FormField label="Lead Time (days)" htmlFor="edit-lead-time">
              <Input
                id="edit-lead-time"
                type="number"
                min={0}
                value={editForm.lead_time_days}
                onChange={(e) => setEditForm((f) => f && { ...f, lead_time_days: Number(e.target.value) })}
              />
            </FormField>
            <FormField label="Working Days" htmlFor="edit-working-days">
              <Input
                id="edit-working-days"
                value={editForm.working_days}
                onChange={(e) => setEditForm((f) => f && { ...f, working_days: e.target.value })}
              />
            </FormField>
            <FormField label="Cutoff Time" htmlFor="edit-cutoff-time">
              <Input
                id="edit-cutoff-time"
                value={editForm.cutoff_time}
                onChange={(e) => setEditForm((f) => f && { ...f, cutoff_time: e.target.value })}
              />
            </FormField>
          </div>
          <FormField label="Notes" htmlFor="edit-notes" hint="Internal-only, never shared with the supplier.">
            <Textarea
              id="edit-notes"
              value={editForm.notes}
              onChange={(e) => setEditForm((f) => f && { ...f, notes: e.target.value })}
            />
          </FormField>
          <label className="flex items-start gap-2 text-sm text-dt-text-primary">
            <input
              type="checkbox"
              className="mt-0.5"
              checked={editForm.is_default ?? false}
              onChange={(e) => setEditForm((f) => f && { ...f, is_default: e.target.checked })}
            />
            <span>
              Island-wide (default) supplier
              <span className="block text-xs text-dt-text-secondary">
                Used automatically when birthday detection can&apos;t match a supplier to a team
                member&apos;s office location. Only one supplier can hold this — setting it here
                clears it on any other.
              </span>
            </span>
          </label>
          <div className="flex justify-end gap-2">
            <Button variant="secondary" size="sm" onClick={() => setEditOpen(false)}>
              Cancel
            </Button>
            <Button
              size="sm"
              loading={updateMutation.isPending}
              onClick={() => editForm && updateMutation.mutate(editForm)}
            >
              Save Changes
            </Button>
          </div>
        </div>
        )}
      </Modal>

      <Modal open={locationOpen} onClose={() => setLocationOpen(false)} title="Add Location">
        <div className="flex flex-col gap-4">
          <FormField label="Office Location" htmlFor="new-location" required>
            <Input
              id="new-location"
              value={newLocation.office_location}
              onChange={(e) => setNewLocation((l) => ({ ...l, office_location: e.target.value }))}
              placeholder="e.g. Colombo"
            />
          </FormField>
          <label className="flex items-center gap-2 text-sm text-dt-text-primary">
            <input
              type="checkbox"
              checked={newLocation.is_primary}
              onChange={(e) => setNewLocation((l) => ({ ...l, is_primary: e.target.checked }))}
            />
            Primary location
          </label>
          <div className="flex justify-end gap-2">
            <Button variant="secondary" size="sm" onClick={() => setLocationOpen(false)}>
              Cancel
            </Button>
            <Button
              size="sm"
              loading={addLocationMutation.isPending}
              disabled={newLocation.office_location.trim() === ""}
              onClick={() => addLocationMutation.mutate()}
            >
              Add Location
            </Button>
          </div>
        </div>
      </Modal>

      <Modal
        open={catalogueOpen}
        onClose={() => setCatalogueOpen(false)}
        title={editingItem ? "Edit Catalogue Item" : "Add Catalogue Item"}
      >
        <div className="flex flex-col gap-4">
          <FormField label="Name" htmlFor="catalogue-name" required>
            <Input
              id="catalogue-name"
              value={catalogueForm.name}
              onChange={(e) => setCatalogueForm((c) => ({ ...c, name: e.target.value }))}
            />
          </FormField>
          <FormField label="Description" htmlFor="catalogue-description">
            <Textarea
              id="catalogue-description"
              value={catalogueForm.description}
              onChange={(e) => setCatalogueForm((c) => ({ ...c, description: e.target.value }))}
            />
          </FormField>
          <label className="flex items-center gap-2 text-sm text-dt-text-primary">
            <input
              type="checkbox"
              checked={catalogueForm.is_active}
              onChange={(e) => setCatalogueForm((c) => ({ ...c, is_active: e.target.checked }))}
            />
            Active
          </label>
          <div className="flex justify-end gap-2">
            <Button variant="secondary" size="sm" onClick={() => setCatalogueOpen(false)}>
              Cancel
            </Button>
            <Button
              size="sm"
              loading={catalogueMutation.isPending}
              disabled={catalogueForm.name.trim() === ""}
              onClick={() => catalogueMutation.mutate()}
            >
              {editingItem ? "Save Changes" : "Add Item"}
            </Button>
          </div>
        </div>
      </Modal>

      <Modal
        open={userModalOpen}
        onClose={() => setUserModalOpen(false)}
        title={editingUser ? "Edit Supplier User" : "Add Supplier User"}
      >
        <div className="flex flex-col gap-4">
          <FormField label="Email" htmlFor="user-email" required>
            <Input
              id="user-email"
              type="email"
              value={userForm.email}
              onChange={(e) => setUserForm((f) => ({ ...f, email: e.target.value }))}
            />
          </FormField>
          <FormField label="Full Name" htmlFor="user-full-name">
            <Input
              id="user-full-name"
              value={userForm.full_name}
              onChange={(e) => setUserForm((f) => ({ ...f, full_name: e.target.value }))}
            />
          </FormField>
          <FormField label="Role" htmlFor="user-role">
            <Select
              id="user-role"
              value={userForm.role}
              onChange={(e) => setUserForm((f) => ({ ...f, role: e.target.value }))}
            >
              <option value="SUPPLIER_USER">Supplier User</option>
              <option value="SUPPLIER_ADMIN">Supplier Admin</option>
            </Select>
          </FormField>
          <FormField label="Status" htmlFor="user-status">
            <Select
              id="user-status"
              value={userForm.status}
              onChange={(e) => setUserForm((f) => ({ ...f, status: e.target.value }))}
            >
              <option value="ACTIVE">Active</option>
              <option value="INACTIVE">Inactive</option>
            </Select>
          </FormField>
          {editingUser && (
            <FormField label="Entra Object ID" htmlFor="user-entra-oid">
              <Input
                id="user-entra-oid"
                value={userForm.entra_object_id ?? ""}
                placeholder="e.g. 00000000-1111-2222-3333-444444444444"
                onChange={(e) => setUserForm((f) => ({ ...f, entra_object_id: e.target.value }))}
              />
              <p className="mt-1 text-xs text-dt-text-secondary">
                {editingUser.entra_object_id
                  ? "Durable Microsoft Entra ID B2B guest identity for this user. Changing it re-points sign-in."
                  : "Not yet linked — until set, this user signs in via the local dev persona picker only. Paste the guest's Entra object id here once provisioned."}
              </p>
            </FormField>
          )}
          <div className="flex justify-end gap-2">
            <Button variant="secondary" size="sm" onClick={() => setUserModalOpen(false)}>
              Cancel
            </Button>
            <Button
              size="sm"
              loading={userMutation.isPending}
              disabled={userForm.email.trim() === ""}
              onClick={() => userMutation.mutate()}
            >
              {editingUser ? "Save Changes" : "Add Supplier User"}
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
