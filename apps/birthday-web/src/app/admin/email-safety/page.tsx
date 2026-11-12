"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ShieldAlert, Plus } from "lucide-react";
import { useState } from "react";
import type { ReactNode } from "react";
import { ApiError, useBirthdayScope } from "@dijione/auth-client";
import {
  Button,
  EmptyState,
  ErrorState,
  FormField,
  Input,
  LoadingState,
  Modal,
  PageHeader,
  Select,
  StatusBadge,
  Table,
  Td,
  Th,
  Thead,
  Tr,
} from "@dijione/design-system";
import {
  createTestEmailRecipient,
  listTestEmailRecipients,
  updateTestEmailRecipient,
} from "@/lib/api";
import type {
  TestEmailRecipientCreateInput,
  TestEmailRecipientOut,
  TestEmailRecipientType,
} from "@dijione/contracts";

// This page is DijiBirthday-owned and non-production-only
// (docs/platform/email-architecture.md). The backend independently
// enforces this with require_non_production() (404 in PROD) on every
// route this page calls — this page's own scope?.isAdmin gate and the
// nav item's is_production check (birthday-shell.tsx) are UI convenience
// only, never the actual security boundary.

const RECIPIENT_TYPE_LABELS: Record<TestEmailRecipientType, string> = {
  INTERNAL_TESTER: "Internal Tester",
  TEST_SUPPLIER: "Test Supplier",
};

type FieldDef = {
  key: string;
  label: string;
  render: (r: TestEmailRecipientOut) => ReactNode;
};

function formatDateTime(iso: string) {
  return new Date(iso).toLocaleString();
}

const FIELDS: FieldDef[] = [
  {
    key: "email_address",
    label: "Email Address",
    render: (r) => <span className="font-medium text-dt-text-primary wrap-break-word">{r.email_address}</span>,
  },
  { key: "display_label", label: "Label", render: (r) => r.display_label || "—" },
  { key: "recipient_type", label: "Type", render: (r) => RECIPIENT_TYPE_LABELS[r.recipient_type] },
  {
    key: "is_active",
    label: "Status",
    render: (r) => <StatusBadge status={r.is_active ? "ACTIVE" : "INACTIVE"} label={r.is_active ? "Active" : "Inactive"} />,
  },
  { key: "created_by", label: "Created By", render: (r) => (r.created_by != null ? `#${r.created_by}` : "—") },
  { key: "created_at", label: "Created At", render: (r) => formatDateTime(r.created_at) },
  {
    key: "updated_by",
    label: "Updated By/At",
    render: (r) => (
      <>
        {r.updated_by != null ? `#${r.updated_by}` : "—"}
        <p className="text-xs text-dt-text-secondary">{formatDateTime(r.updated_at)}</p>
      </>
    ),
  },
];

const EMPTY_FORM: TestEmailRecipientCreateInput = {
  email_address: "",
  display_label: "",
  recipient_type: "INTERNAL_TESTER",
  is_active: true,
};

function RecipientCard({
  recipient,
  onEdit,
  onToggleActive,
  toggling,
}: {
  recipient: TestEmailRecipientOut;
  onEdit: () => void;
  onToggleActive: () => void;
  toggling: boolean;
}) {
  return (
    <div className="rounded-2xl border border-dt-border bg-dt-surface p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <span className="min-w-0 font-medium text-dt-text-primary wrap-break-word">{recipient.email_address}</span>
        <StatusBadge status={recipient.is_active ? "ACTIVE" : "INACTIVE"} label={recipient.is_active ? "Active" : "Inactive"} />
      </div>
      <div className="mt-3 grid grid-cols-2 gap-x-4 gap-y-3">
        <div className="min-w-0">
          <p className="text-[11px] font-medium uppercase tracking-wide text-dt-text-secondary">Label</p>
          <p className="mt-0.5 text-sm text-dt-text-primary">{recipient.display_label || "—"}</p>
        </div>
        <div className="min-w-0">
          <p className="text-[11px] font-medium uppercase tracking-wide text-dt-text-secondary">Type</p>
          <p className="mt-0.5 text-sm text-dt-text-primary">{RECIPIENT_TYPE_LABELS[recipient.recipient_type]}</p>
        </div>
        <div className="min-w-0">
          <p className="text-[11px] font-medium uppercase tracking-wide text-dt-text-secondary">Created</p>
          <p className="mt-0.5 text-sm text-dt-text-primary">{formatDateTime(recipient.created_at)}</p>
        </div>
        <div className="min-w-0">
          <p className="text-[11px] font-medium uppercase tracking-wide text-dt-text-secondary">Updated</p>
          <p className="mt-0.5 text-sm text-dt-text-primary">{formatDateTime(recipient.updated_at)}</p>
        </div>
      </div>
      <div className="mt-4 flex flex-wrap gap-2">
        <Button size="sm" variant="secondary" onClick={onEdit}>
          Edit
        </Button>
        <Button size="sm" variant="secondary" loading={toggling} onClick={onToggleActive}>
          {recipient.is_active ? "Deactivate" : "Activate"}
        </Button>
      </div>
    </div>
  );
}

export default function EmailSafetyPage() {
  const scope = useBirthdayScope();
  const queryClient = useQueryClient();
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<TestEmailRecipientOut | null>(null);
  const [form, setForm] = useState<TestEmailRecipientCreateInput>(EMPTY_FORM);
  const [formError, setFormError] = useState<string | null>(null);

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["birthday-test-email-recipients"],
    queryFn: () => listTestEmailRecipients(),
    enabled: !!scope?.isAdmin,
  });
  const recipientList = data?.items ?? [];

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["birthday-test-email-recipients"] });

  const createMutation = useMutation({
    mutationFn: (payload: TestEmailRecipientCreateInput) => createTestEmailRecipient(payload),
    onSuccess: () => {
      invalidate();
      closeModal();
    },
    onError: (err: unknown) => setFormError(err instanceof ApiError ? err.message : "Could not save this recipient."),
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: Partial<TestEmailRecipientCreateInput> }) =>
      updateTestEmailRecipient(id, payload),
    onSuccess: () => {
      invalidate();
      closeModal();
    },
    onError: (err: unknown) => setFormError(err instanceof ApiError ? err.message : "Could not save this recipient."),
  });

  const toggleMutation = useMutation({
    mutationFn: ({ id, is_active }: { id: number; is_active: boolean }) => updateTestEmailRecipient(id, { is_active }),
    onSuccess: invalidate,
  });

  function openCreate() {
    setEditing(null);
    setForm(EMPTY_FORM);
    setFormError(null);
    setModalOpen(true);
  }

  function openEdit(recipient: TestEmailRecipientOut) {
    setEditing(recipient);
    setForm({
      email_address: recipient.email_address,
      display_label: recipient.display_label,
      recipient_type: recipient.recipient_type,
      is_active: recipient.is_active,
    });
    setFormError(null);
    setModalOpen(true);
  }

  function closeModal() {
    setModalOpen(false);
    setEditing(null);
    setForm(EMPTY_FORM);
    setFormError(null);
  }

  const trimmedEmail = form.email_address.trim();
  // Client-side is a UX convenience only — the backend re-validates syntax,
  // duplicates (case-insensitively) and rejects wildcards regardless
  // (app/services/test_email_recipient_service.py); this never replaces
  // that server-side check.
  const emailLooksValid = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(trimmedEmail);

  function submit() {
    setFormError(null);
    if (!emailLooksValid) {
      setFormError("Enter a valid email address.");
      return;
    }
    if (editing) {
      updateMutation.mutate({
        id: editing.id,
        payload: { display_label: form.display_label, recipient_type: form.recipient_type },
      });
    } else {
      createMutation.mutate({ ...form, email_address: trimmedEmail });
    }
  }

  const saving = createMutation.isPending || updateMutation.isPending;

  if (!scope?.isAdmin) {
    return (
      <EmptyState
        title="Admin access required"
        description="Email Safety is only available to DijiBirthday internal administrators."
      />
    );
  }

  return (
    <div>
      <PageHeader
        title="Email Safety"
        description="Manage which recipients DijiBirthday is allowed to send real outbound email to in this environment."
        action={
          <Button size="sm" onClick={openCreate}>
            <Plus className="size-4" />
            Add Recipient
          </Button>
        }
      />

      <div className="mb-6 flex items-start gap-3 rounded-2xl border border-dt-warning/25 bg-[color-mix(in_srgb,var(--dt-warning)_10%,white)] p-4">
        <ShieldAlert className="mt-0.5 size-5 shrink-0 text-dt-warning" />
        <div>
          <p className="text-sm font-medium text-dt-text-primary">
            Test Email Safety is active in this environment. Only approved recipients can receive real outbound
            DijiBirthday email.
          </p>
          <p className="mt-1 text-xs text-dt-text-secondary">
            This control only applies in non-production environments. It never appears, and is never enforced, in
            production — production supplier email is never restricted by this list.
          </p>
        </div>
      </div>

      {isLoading ? (
        <LoadingState label="Loading approved recipients…" />
      ) : isError || !data ? (
        <ErrorState onRetry={() => refetch()} />
      ) : recipientList.length === 0 ? (
        <EmptyState
          title="No approved recipients yet"
          description="Add an internal tester or test supplier address to allow real outbound email to it."
        />
      ) : (
        <>
          <div className="hidden overflow-x-auto lg:block">
            <Table>
              <Thead>
                <Tr>
                  {FIELDS.map((f) => (
                    <Th key={f.key}>{f.label}</Th>
                  ))}
                  <Th>Actions</Th>
                </Tr>
              </Thead>
              <tbody>
                {recipientList.map((r) => (
                  <Tr key={r.id}>
                    {FIELDS.map((f) => (
                      <Td key={f.key}>{f.render(r)}</Td>
                    ))}
                    <Td>
                      <div className="flex flex-wrap gap-2">
                        <Button size="sm" variant="secondary" onClick={() => openEdit(r)}>
                          Edit
                        </Button>
                        <Button
                          size="sm"
                          variant="secondary"
                          loading={toggleMutation.isPending && toggleMutation.variables?.id === r.id}
                          onClick={() => toggleMutation.mutate({ id: r.id, is_active: !r.is_active })}
                        >
                          {r.is_active ? "Deactivate" : "Activate"}
                        </Button>
                      </div>
                    </Td>
                  </Tr>
                ))}
              </tbody>
            </Table>
          </div>

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:hidden">
            {recipientList.map((r) => (
              <RecipientCard
                key={r.id}
                recipient={r}
                onEdit={() => openEdit(r)}
                toggling={toggleMutation.isPending && toggleMutation.variables?.id === r.id}
                onToggleActive={() => toggleMutation.mutate({ id: r.id, is_active: !r.is_active })}
              />
            ))}
          </div>
        </>
      )}

      <Modal open={modalOpen} onClose={closeModal} title={editing ? "Edit Recipient" : "Add Recipient"}>
        <div className="flex flex-col gap-4">
          <FormField label="Email Address" htmlFor="recipient-email" required>
            <Input
              id="recipient-email"
              type="email"
              value={form.email_address}
              disabled={!!editing}
              onChange={(e) => setForm((f) => ({ ...f, email_address: e.target.value }))}
              placeholder="name@example.com"
            />
          </FormField>
          {editing && (
            <p className="-mt-2 text-xs text-dt-text-secondary">
              The address itself cannot be changed here — remove this recipient and add the correct address instead.
            </p>
          )}
          <FormField label="Label" htmlFor="recipient-label" hint="A short description, e.g. who this address belongs to.">
            <Input
              id="recipient-label"
              value={form.display_label}
              onChange={(e) => setForm((f) => ({ ...f, display_label: e.target.value }))}
              placeholder="e.g. Madushanka - Internal Test"
            />
          </FormField>
          <FormField label="Type" htmlFor="recipient-type" required>
            <Select
              id="recipient-type"
              value={form.recipient_type}
              onChange={(e) => setForm((f) => ({ ...f, recipient_type: e.target.value as TestEmailRecipientType }))}
            >
              <option value="INTERNAL_TESTER">Internal Tester</option>
              <option value="TEST_SUPPLIER">Test Supplier</option>
            </Select>
          </FormField>
          {formError && <p className="text-sm text-dt-danger">{formError}</p>}
          <div className="flex justify-end gap-2">
            <Button variant="secondary" size="sm" onClick={closeModal}>
              Cancel
            </Button>
            <Button size="sm" loading={saving} disabled={!emailLooksValid} onClick={submit}>
              {editing ? "Save Changes" : "Add Recipient"}
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
