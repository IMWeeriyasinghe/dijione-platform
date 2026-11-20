"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { RefreshCw, RotateCcw, Send, Trash2 } from "lucide-react";
import {
  ApiError,
  addEmailTestRecipient,
  dispatchNotificationsNow,
  getEmailOutboxItem,
  getNotificationSummary,
  listEmailOutbox,
  listEmailTestRecipients,
  listNotificationEvents,
  removeEmailTestRecipient,
  retryEmailOutboxItem,
  setNotificationEvent,
  type EmailStatus,
  type NotificationSummary,
  type OutboxFilters,
} from "@/lib/api";
import {
  Button,
  Card,
  EmptyState,
  ErrorState,
  FormField,
  Input,
  LoadingState,
  Modal,
  PageHeader,
  Select,
  Table,
  Td,
  Th,
  Thead,
  Tr,
  formatDateTime,
} from "@dijione/design-system";

const PAGE_SIZE = 50;

const EVENT_LABELS: Record<string, string> = {
  "access.welcome": "Access available",
  "access.granted": "Access granted",
  "access.revoked": "Access revoked",
  "access.updated": "Access updated",
  "account.deactivated": "Account deactivated",
};

const STATUS_HELP: Record<EmailStatus, string> = {
  PENDING: "Waiting to be sent",
  SENDING: "Being sent now",
  RETRY: "A send attempt failed; another is scheduled",
  SUBMITTED: "Accepted by Microsoft Graph (not a delivery confirmation)",
  SIMULATED: "Not sent: this environment does not send real email",
  FAILED: "All send attempts failed",
  BLOCKED: "Not sent: recipient is not an approved test recipient",
  DISABLED: "Not sent: email sending is disabled in this environment",
  SUPERSEDED: "Replaced by a later email covering the same change",
  SKIPPED: "Not sent: the event was switched off",
};

const STATUS_TONE: Record<EmailStatus, string> = {
  PENDING: "bg-dt-surface-warm text-dt-text-secondary border-dt-border",
  SENDING: "bg-dt-cream text-dt-burnt-orange border-dt-border",
  RETRY: "bg-amber-50 text-dt-warning border-amber-200",
  SUBMITTED: "bg-green-50 text-dt-success border-green-200",
  SIMULATED: "bg-dt-surface-warm text-dt-text-secondary border-dt-border",
  FAILED: "bg-red-50 text-dt-danger border-red-200",
  BLOCKED: "bg-amber-50 text-dt-warning border-amber-200",
  DISABLED: "bg-dt-surface-warm text-dt-text-secondary border-dt-border",
  SUPERSEDED: "bg-dt-surface-warm text-dt-text-secondary border-dt-border",
  SKIPPED: "bg-dt-surface-warm text-dt-text-secondary border-dt-border",
};

function EmailStatusBadge({ status }: { status: EmailStatus }) {
  return (
    <span
      title={STATUS_HELP[status]}
      className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium ${STATUS_TONE[status]}`}
    >
      {status.charAt(0) + status.slice(1).toLowerCase()}
    </span>
  );
}

function errorText(e: unknown, fallback: string) {
  return e instanceof ApiError ? e.message : fallback;
}

function EnvironmentBanner({ summary }: { summary: NotificationSummary }) {
  const mode = {
    simulated: "Simulated — no email leaves this environment.",
    internal_allowlist: "Test recipients only — email is sent only to the approved test recipients below.",
    production: "Live — email is sent to the people concerned.",
    disabled: "Disabled — email sending is switched off in this environment.",
  }[summary.effective_policy];
  return (
    <Card className="mb-6 p-4">
      <div className="flex flex-col gap-1 text-sm sm:flex-row sm:flex-wrap sm:gap-x-6">
        <span>
          <span className="text-dt-text-secondary">Environment: </span>
          <strong>{summary.environment}</strong>
        </span>
        <span>
          <span className="text-dt-text-secondary">Sending: </span>
          <strong>{mode}</strong>
        </span>
        {summary.sender_mailbox && (
          <span>
            <span className="text-dt-text-secondary">Sender: </span>
            <strong className="break-all">{summary.sender_mailbox}</strong>
          </span>
        )}
        {!summary.access_notifications_enabled && (
          <span className="text-dt-warning">Access notifications are switched off for this environment.</span>
        )}
      </div>
    </Card>
  );
}

function DetailModal({ id, onClose }: { id: number | null; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const detail = useQuery({
    queryKey: ["admin", "notifications", "item", id],
    queryFn: () => getEmailOutboxItem(id as number),
    enabled: id !== null,
  });
  const retry = useMutation({
    mutationFn: () => retryEmailOutboxItem(id as number),
    onSuccess: () => {
      setError(null);
      queryClient.invalidateQueries({ queryKey: ["admin", "notifications"] });
    },
    onError: (e) => setError(errorText(e, "Could not retry this email.")),
  });
  const item = detail.data;
  return (
    <Modal open={id !== null} onClose={onClose} title="Email details">
      {detail.isLoading && <LoadingState label="Loading…" />}
      {detail.isError && <ErrorState message="Could not load this email." onRetry={() => detail.refetch()} />}
      {item && (
        <div className="flex flex-col gap-3 text-sm">
          <dl className="grid grid-cols-1 gap-x-4 gap-y-2 sm:grid-cols-[10rem_1fr]">
            <dt className="text-dt-text-secondary">Subject</dt>
            <dd className="break-words">{item.subject}</dd>
            <dt className="text-dt-text-secondary">Recipient</dt>
            <dd className="break-all">{item.recipient_email}</dd>
            <dt className="text-dt-text-secondary">Event</dt>
            <dd>{EVENT_LABELS[item.event_type] ?? item.event_type}</dd>
            <dt className="text-dt-text-secondary">Status</dt>
            <dd className="flex flex-col gap-1">
              <EmailStatusBadge status={item.status} />
              <span className="text-xs text-dt-text-secondary">{STATUS_HELP[item.status]}</span>
            </dd>
            <dt className="text-dt-text-secondary">Attempts</dt>
            <dd>
              {item.attempts} of {item.max_attempts}
            </dd>
            <dt className="text-dt-text-secondary">Queued</dt>
            <dd>{formatDateTime(item.created_at)}</dd>
            {item.last_attempt_at && (
              <>
                <dt className="text-dt-text-secondary">Last attempt</dt>
                <dd>{formatDateTime(item.last_attempt_at)}</dd>
              </>
            )}
            <dt className="text-dt-text-secondary">Correlation ID</dt>
            <dd className="break-all font-mono text-xs">{item.correlation_id}</dd>
            {item.graph_request_id && (
              <>
                <dt className="text-dt-text-secondary">Graph request ID</dt>
                <dd className="break-all font-mono text-xs">{item.graph_request_id}</dd>
              </>
            )}
          </dl>
          {item.last_error && (
            <div>
              <p className="mb-1 text-dt-text-secondary">Last error</p>
              <pre className="max-h-48 overflow-auto whitespace-pre-wrap break-words rounded bg-dt-surface-warm p-2 text-xs">
                {item.last_error}
              </pre>
            </div>
          )}
          {error && <p className="text-dt-danger">{error}</p>}
          <div className="flex justify-end gap-2">
            <Button variant="secondary" onClick={onClose}>
              Close
            </Button>
            {item.can_retry && (
              <Button onClick={() => retry.mutate()} loading={retry.isPending}>
                <RotateCcw className="h-4 w-4" aria-hidden />
                Retry
              </Button>
            )}
          </div>
        </div>
      )}
    </Modal>
  );
}

function HistoryTab({ summary }: { summary: NotificationSummary }) {
  const queryClient = useQueryClient();
  const [filters, setFilters] = useState<OutboxFilters>({ limit: PAGE_SIZE, offset: 0 });
  const [recipient, setRecipient] = useState("");
  const [selected, setSelected] = useState<number | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const outbox = useQuery({
    queryKey: ["admin", "notifications", "outbox", filters],
    queryFn: () => listEmailOutbox(filters),
  });
  const dispatch = useMutation({
    mutationFn: dispatchNotificationsNow,
    onSuccess: (r) => {
      const n = Object.values(r.processed).reduce((a, b) => a + b, 0);
      setMessage(n ? `Processed ${n} email${n === 1 ? "" : "s"}.` : "Nothing was due.");
      queryClient.invalidateQueries({ queryKey: ["admin", "notifications"] });
    },
    onError: (e) => setMessage(errorText(e, "Could not process emails.")),
  });
  const update = (patch: OutboxFilters) => setFilters((f) => ({ ...f, ...patch, offset: 0 }));
  const offset = filters.offset ?? 0;
  const total = outbox.data?.total ?? 0;

  return (
    <div>
      <div className="mb-4 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-5">
        <FormField label="Application" htmlFor="f-app">
          <Select id="f-app" value={filters.application ?? ""} onChange={(e) => update({ application: e.target.value || undefined })}>
            <option value="">All</option>
            {summary.applications.map((a) => (
              <option key={a.key} value={a.key}>
                {a.name}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField label="Event" htmlFor="f-event">
          <Select id="f-event" value={filters.event_type ?? ""} onChange={(e) => update({ event_type: e.target.value || undefined })}>
            <option value="">All</option>
            {Object.entries(EVENT_LABELS).map(([k, v]) => (
              <option key={k} value={k}>
                {v}
              </option>
            ))}
          </Select>
        </FormField>
        <FormField label="Status" htmlFor="f-status">
          <Select id="f-status" value={filters.status ?? ""} onChange={(e) => update({ status: e.target.value || undefined })}>
            <option value="">All</option>
            {summary.statuses.map((s) => (
              <option key={s} value={s}>
                {s.charAt(0) + s.slice(1).toLowerCase()} ({summary.counts[s] ?? 0})
              </option>
            ))}
          </Select>
        </FormField>
        <FormField label="Recipient" htmlFor="f-recipient">
          <Input
            id="f-recipient"
            value={recipient}
            placeholder="name@…"
            onChange={(e) => setRecipient(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && update({ recipient: recipient.trim() || undefined })}
            onBlur={() => update({ recipient: recipient.trim() || undefined })}
          />
        </FormField>
        <div className="flex items-end gap-2">
          <Button variant="secondary" onClick={() => outbox.refetch()} aria-label="Refresh">
            <RefreshCw className="h-4 w-4" aria-hidden />
          </Button>
          <Button variant="secondary" onClick={() => dispatch.mutate()} loading={dispatch.isPending}>
            <Send className="h-4 w-4" aria-hidden />
            Process now
          </Button>
        </div>
      </div>
      {message && <p className="mb-3 text-sm text-dt-text-secondary">{message}</p>}
      {outbox.isLoading && <LoadingState label="Loading delivery history…" />}
      {outbox.isError && <ErrorState message="Could not load delivery history." onRetry={() => outbox.refetch()} />}
      {outbox.data && outbox.data.items.length === 0 && (
        <EmptyState title="No emails" description="Emails appear here when a person's access changes." />
      )}
      {outbox.data && outbox.data.items.length > 0 && (
        <>
          <div className="overflow-x-auto">
            <Table>
              <Thead>
                <tr>
                  <Th>Queued</Th>
                  <Th>Recipient</Th>
                  <Th>Subject</Th>
                  <Th>Status</Th>
                  <Th>Attempts</Th>
                  <Th>
                    <span className="sr-only">Actions</span>
                  </Th>
                </tr>
              </Thead>
              <tbody>
                {outbox.data.items.map((item) => (
                  <Tr key={item.id}>
                    <Td className="whitespace-nowrap text-sm text-dt-text-secondary">{formatDateTime(item.created_at)}</Td>
                    <Td className="max-w-[14rem] truncate text-sm" title={item.recipient_email}>
                      {item.recipient_email}
                    </Td>
                    <Td className="max-w-xs truncate text-sm" title={item.subject}>
                      {item.subject}
                    </Td>
                    <Td>
                      <EmailStatusBadge status={item.status} />
                    </Td>
                    <Td className="text-sm">
                      {item.attempts}/{item.max_attempts}
                    </Td>
                    <Td className="text-right">
                      <Button variant="ghost" size="sm" onClick={() => setSelected(item.id)}>
                        Details
                      </Button>
                    </Td>
                  </Tr>
                ))}
              </tbody>
            </Table>
          </div>
          <div className="mt-3 flex items-center justify-between text-sm text-dt-text-secondary">
            <span>
              {offset + 1}–{Math.min(offset + PAGE_SIZE, total)} of {total}
            </span>
            <div className="flex gap-2">
              <Button variant="secondary" size="sm" disabled={offset === 0}
                onClick={() => setFilters((f) => ({ ...f, offset: Math.max(0, offset - PAGE_SIZE) }))}>
                Previous
              </Button>
              <Button variant="secondary" size="sm" disabled={offset + PAGE_SIZE >= total}
                onClick={() => setFilters((f) => ({ ...f, offset: offset + PAGE_SIZE }))}>
                Next
              </Button>
            </div>
          </div>
        </>
      )}
      <DetailModal id={selected} onClose={() => setSelected(null)} />
    </div>
  );
}

function EventsTab() {
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const events = useQuery({ queryKey: ["admin", "notifications", "events"], queryFn: listNotificationEvents });
  const toggle = useMutation({
    mutationFn: ({ eventType, enabled }: { eventType: string; enabled: boolean }) => setNotificationEvent(eventType, enabled),
    onSuccess: (data) => {
      setError(null);
      queryClient.setQueryData(["admin", "notifications", "events"], data);
    },
    onError: (e) => setError(errorText(e, "Could not change this event.")),
  });
  if (events.isLoading) return <LoadingState label="Loading events…" />;
  if (events.isError) return <ErrorState message="Could not load events." onRetry={() => events.refetch()} />;
  return (
    <div className="flex flex-col gap-3">
      {error && <p className="text-sm text-dt-danger">{error}</p>}
      {events.data?.map((ev) => (
        <Card key={ev.event_type} className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="min-w-0">
            <p className="font-medium">{EVENT_LABELS[ev.event_type] ?? ev.event_type}</p>
            <p className="text-sm text-dt-text-secondary">{ev.description}</p>
            <p className="mt-1 break-words font-mono text-xs text-dt-text-secondary">{ev.subject}</p>
          </div>
          <label className="flex shrink-0 cursor-pointer items-center gap-2 text-sm">
            <input
              type="checkbox"
              className="h-4 w-4 accent-dt-orange"
              checked={ev.enabled}
              disabled={toggle.isPending}
              onChange={(e) => toggle.mutate({ eventType: ev.event_type, enabled: e.target.checked })}
            />
            {ev.enabled ? "On" : "Off"}
          </label>
        </Card>
      ))}
    </div>
  );
}

function RecipientsTab({ summary }: { summary: NotificationSummary }) {
  const queryClient = useQueryClient();
  const [address, setAddress] = useState("");
  const [label, setLabel] = useState("");
  const [error, setError] = useState<string | null>(null);
  const recipients = useQuery({ queryKey: ["admin", "notifications", "recipients"], queryFn: listEmailTestRecipients });
  const onDone = (data: unknown) => {
    setError(null);
    queryClient.setQueryData(["admin", "notifications", "recipients"], data);
  };
  const add = useMutation({
    mutationFn: () => addEmailTestRecipient(address.trim(), label.trim()),
    onSuccess: (data) => {
      onDone(data);
      setAddress("");
      setLabel("");
    },
    onError: (e) => setError(errorText(e, "Could not add this recipient.")),
  });
  const remove = useMutation({
    mutationFn: (id: number) => removeEmailTestRecipient(id),
    onSuccess: onDone,
    onError: (e) => setError(errorText(e, "Could not remove this recipient.")),
  });

  return (
    <div>
      <p className="mb-4 text-sm text-dt-text-secondary">
        {summary.is_production
          ? "This is a production environment: the test recipient list is not used here."
          : "In DEV and UAT, email is only sent to these individual addresses. Everyone else is blocked."}
      </p>
      <Card className="mb-4 grid grid-cols-1 gap-3 p-4 sm:grid-cols-[1fr_1fr_auto] sm:items-end">
        <FormField label="Email address" htmlFor="r-address" required>
          <Input id="r-address" value={address} onChange={(e) => setAddress(e.target.value)} placeholder="tester@dijitalteam.com" />
        </FormField>
        <FormField label="Label" htmlFor="r-label">
          <Input id="r-label" value={label} onChange={(e) => setLabel(e.target.value)} placeholder="QA mailbox" />
        </FormField>
        <Button onClick={() => add.mutate()} loading={add.isPending} disabled={!address.trim()}>
          Add
        </Button>
      </Card>
      {error && <p className="mb-3 text-sm text-dt-danger">{error}</p>}
      {recipients.isLoading && <LoadingState label="Loading recipients…" />}
      {recipients.isError && <ErrorState message="Could not load recipients." onRetry={() => recipients.refetch()} />}
      {recipients.data && recipients.data.length === 0 && (
        <EmptyState title="No test recipients" description="No email can be sent in DEV or UAT until a recipient is added." />
      )}
      {recipients.data && recipients.data.length > 0 && (
        <div className="overflow-x-auto">
          <Table>
            <Thead>
              <tr>
                <Th>Address</Th>
                <Th>Label</Th>
                <Th>Added</Th>
                <Th>
                  <span className="sr-only">Actions</span>
                </Th>
              </tr>
            </Thead>
            <tbody>
              {recipients.data.map((r) => (
                <Tr key={r.id}>
                  <Td className="break-all text-sm">{r.address}</Td>
                  <Td className="text-sm text-dt-text-secondary">{r.label || "—"}</Td>
                  <Td className="whitespace-nowrap text-sm text-dt-text-secondary">{formatDateTime(r.created_at)}</Td>
                  <Td className="text-right">
                    <Button variant="ghost" size="sm" aria-label={`Remove ${r.address}`}
                      onClick={() => remove.mutate(r.id)} disabled={remove.isPending}>
                      <Trash2 className="h-4 w-4" aria-hidden />
                    </Button>
                  </Td>
                </Tr>
              ))}
            </tbody>
          </Table>
        </div>
      )}
    </div>
  );
}

const TABS = [
  { key: "history", label: "Delivery history" },
  { key: "events", label: "Events" },
  { key: "recipients", label: "Test recipients" },
] as const;

export default function NotificationsPage() {
  const [tab, setTab] = useState<(typeof TABS)[number]["key"]>("history");
  const summary = useQuery({ queryKey: ["admin", "notifications", "summary"], queryFn: getNotificationSummary });

  return (
    <div>
      <PageHeader
        title="Notifications"
        description="Email notifications DijiOne sends when a person's access changes: delivery history, event switches and the DEV/UAT test recipient list."
      />
      {summary.isLoading && <LoadingState label="Loading…" />}
      {summary.isError && (
        <ErrorState message="Could not load notification settings. You may not have permission to view them."
          onRetry={() => summary.refetch()} />
      )}
      {summary.data && (
        <>
          <EnvironmentBanner summary={summary.data} />
          <div role="tablist" aria-label="Notifications" className="mb-4 flex gap-1 overflow-x-auto border-b border-dt-border">
            {TABS.map((t) => (
              <button
                key={t.key}
                role="tab"
                aria-selected={tab === t.key}
                onClick={() => setTab(t.key)}
                className={`whitespace-nowrap border-b-2 px-3 py-2 text-sm font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-dt-orange ${
                  tab === t.key ? "border-dt-orange text-dt-text-primary" : "border-transparent text-dt-text-secondary hover:text-dt-text-primary"
                }`}
              >
                {t.label}
              </button>
            ))}
          </div>
          {tab === "history" && <HistoryTab summary={summary.data} />}
          {tab === "events" && <EventsTab />}
          {tab === "recipients" && <RecipientsTab summary={summary.data} />}
        </>
      )}
    </div>
  );
}
