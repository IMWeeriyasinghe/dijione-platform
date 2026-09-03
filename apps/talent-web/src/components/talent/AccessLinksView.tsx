"use client";

import {
  Button,
  Card,
  EmptyState,
  ErrorState,
  FormField,
  Input,
  LoadingState,
  PageHeader,
  Select,
  StatusBadge,
  Table,
  Td,
  Th,
  Thead,
  Tr,
} from "@dijione/design-system";
import type { MagicLinkGrantCreatedOut } from "@dijione/contracts";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import {
  createMagicLinkGrant,
  extendMagicLinkGrant,
  listClientPortfolios,
  listMagicLinkGrants,
  regenerateMagicLinkGrant,
  revokeMagicLinkGrant,
} from "@/lib/api";

const MIN_EXPIRY_DAYS = 1;
const MAX_EXPIRY_DAYS = 90;
const DEFAULT_EXPIRY_DAYS = 14;
// In-session-only recall of the last generated link (plan §H4 option E) —
// never a server-side store of the raw token. Cleared on Dismiss or when
// the tab/session ends; a viewer of this browser's localStorage after that
// finds nothing, since sessionStorage does not persist across tabs/reloads
// of a closed session.
const SESSION_KEY = "talentflow.freshAccessLink";

function fmt(value: string | null): string {
  if (!value) return "—";
  return new Date(value).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

// Both of these work in ONE consistent time frame (local wall-clock day),
// start to finish — never round-tripping a date-only value through
// toISOString()/UTC partway. That round-trip is what caused the bug: in a
// positive-UTC-offset timezone (e.g. late evening in Asia/Australia),
// today's UTC calendar date is already tomorrow's local date, so the
// offered `min` and the value actually submitted disagreed by up to a
// day — occasionally landing outside the backend's own [1, 90]-day bound
// and turning a date the picker itself offered into a 400.
function dateInputValue(daysFromNow: number): string {
  const d = new Date();
  d.setDate(d.getDate() + daysFromNow);
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

export function endOfDayIso(dateStr: string): string {
  // Parsed as local time (no "Z"/offset suffix) — the same frame
  // dateInputValue's Y/M/D came from.
  return new Date(`${dateStr}T23:59:59`).toISOString();
}

// The date picker offers whole calendar days, but a submitted value is
// end-of-that-day (23:59:59 local) — up to ~24h off "the same instant N
// days from now" the backend actually bounds against
// (MagicLinkService._resolve_expiry: now + [1, 90] days, a fixed
// millisecond duration). So the picker's own min/max must each be pulled
// a whole day *inside* the raw N-day mark: end-of-day-of-day-(N-1) is at
// most ~1 real second past the raw N-day duration and can go negative
// when a DST transition falls inside the forward window (local
// calendar-day arithmetic stretches/shrinks by the DST hour relative to
// the backend's fixed-duration bound). A full extra day of buffer on
// each side restores a real ~24h margin that comfortably absorbs a ±1h
// DST shift plus ordinary request latency.
//
//   min offered = day 2   (MIN_EXPIRY_DAYS + 1) — end-of-day is always
//                          well past the backend's now+1-day floor even
//                          after a spring-forward inside the window.
//   max offered = day 88  (MAX_EXPIRY_DAYS - 2) — end-of-day is always
//                          well under the backend's now+90-day ceiling
//                          even after a fall-back inside the window.
//
// Exported for the timezone-consistency regression tests.
export function minSelectableDate(): string {
  return dateInputValue(MIN_EXPIRY_DAYS + 1);
}

export function maxSelectableDate(): string {
  return dateInputValue(MAX_EXPIRY_DAYS - 2);
}

function daysUntil(iso: string): number {
  return Math.ceil((new Date(iso).getTime() - Date.now()) / 86_400_000);
}

function ExpiryHint({ status, expiresAt }: { status: string; expiresAt: string }) {
  if (status !== "ACTIVE") return <span>{fmt(expiresAt)}</span>;
  const days = daysUntil(expiresAt);
  const label = days <= 0 ? "today" : days === 1 ? "in 1 day" : `in ${days} days`;
  return (
    <div>
      <div>{fmt(expiresAt)}</div>
      <div className={days <= 3 ? "text-xs font-medium text-dt-warning" : "text-xs text-dt-text-secondary"}>
        {label}
      </div>
    </div>
  );
}

function OneTimeLinkPanel({
  grant,
  onDismiss,
}: {
  grant: MagicLinkGrantCreatedOut;
  onDismiss: () => void;
}) {
  const [copied, setCopied] = useState(false);
  return (
    <Card className="mb-6 border-dt-orange/40 bg-dt-surface-warm p-5">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <h3 className="text-sm font-semibold text-dt-text-primary">
            Access link for {grant.client_name}
          </h3>
          <p className="mt-1 text-xs text-dt-warning">
            Shown once. Copy it now — it cannot be retrieved again from the server. You can still
            re-copy it below for the rest of this browser session.
          </p>
          <code className="mt-2 block break-all rounded-md bg-dt-surface px-3 py-2 text-xs text-dt-text-primary">
            {grant.access_url}
          </code>
        </div>
        <div className="flex shrink-0 flex-col gap-2">
          <Button
            size="sm"
            onClick={() => {
              void navigator.clipboard?.writeText(grant.access_url);
              setCopied(true);
              setTimeout(() => setCopied(false), 3000);
            }}
          >
            {copied ? "Copied" : "Copy link"}
          </Button>
          <Button size="sm" variant="ghost" onClick={onDismiss}>
            Dismiss
          </Button>
        </div>
      </div>
    </Card>
  );
}

export function AccessLinksView() {
  const qc = useQueryClient();
  const [clientId, setClientId] = useState<number | null>(null);
  const [contactName, setContactName] = useState("");
  const [contactEmail, setContactEmail] = useState("");
  const [expiryDate, setExpiryDate] = useState(() => dateInputValue(DEFAULT_EXPIRY_DAYS));
  // Hydrate the just-generated link from this browser tab's own session
  // storage (survives a reload of the same tab; never sent anywhere,
  // never written server-side). A lazy initializer, not an effect —
  // sessionStorage is synchronous and only ever available client-side, so
  // there is nothing to "synchronize" after mount.
  const [freshLink, setFreshLink] = useState<MagicLinkGrantCreatedOut | null>(() => {
    if (typeof window === "undefined") return null;
    try {
      const raw = sessionStorage.getItem(SESSION_KEY);
      return raw ? JSON.parse(raw) : null;
    } catch {
      return null;
    }
  });
  const [extendingId, setExtendingId] = useState<string | null>(null);
  const [extendDate, setExtendDate] = useState("");

  function rememberFreshLink(grant: MagicLinkGrantCreatedOut | null) {
    setFreshLink(grant);
    try {
      if (grant) sessionStorage.setItem(SESSION_KEY, JSON.stringify(grant));
      else sessionStorage.removeItem(SESSION_KEY);
    } catch {
      /* best-effort only */
    }
  }

  const clients = useQuery({ queryKey: ["client-portfolios"], queryFn: listClientPortfolios });
  const grants = useQuery({
    queryKey: ["magic-link-grants"],
    queryFn: () => listMagicLinkGrants(),
  });

  const invalidate = () => qc.invalidateQueries({ queryKey: ["magic-link-grants"] });

  const create = useMutation({
    mutationFn: () =>
      createMagicLinkGrant({
        client_id: clientId as number,
        contact_name: contactName.trim() || undefined,
        contact_email: contactEmail.trim() || undefined,
        expires_at: endOfDayIso(expiryDate),
      }),
    onSuccess: (grant) => {
      rememberFreshLink(grant);
      setContactName("");
      setContactEmail("");
      setExpiryDate(dateInputValue(DEFAULT_EXPIRY_DAYS));
      invalidate();
    },
  });

  const revoke = useMutation({
    mutationFn: (publicId: string) => revokeMagicLinkGrant(publicId),
    onSuccess: invalidate,
  });

  const regenerate = useMutation({
    mutationFn: (publicId: string) => regenerateMagicLinkGrant(publicId),
    onSuccess: (grant) => {
      rememberFreshLink(grant);
      invalidate();
    },
  });

  const extend = useMutation({
    mutationFn: ({ publicId, expiresAt }: { publicId: string; expiresAt: string }) =>
      extendMagicLinkGrant(publicId, expiresAt),
    onSuccess: () => {
      setExtendingId(null);
      invalidate();
    },
  });

  return (
    <div>
      <PageHeader
        title="Client Access Links"
        description="Generate a secure magic link that lets a client (or prospect) open the Client Talent Review Workspace — a read-only view of their own approved candidates and progress. No login is provisioned; the link is the credential. Revoke at any time."
      />

      {freshLink && (
        <OneTimeLinkPanel grant={freshLink} onDismiss={() => rememberFreshLink(null)} />
      )}

      <Card className="mb-6 p-6">
        <h2 className="text-base font-semibold text-dt-text-primary">Generate a client access link</h2>
        <p className="mt-1 text-sm text-dt-text-secondary">
          One link per client contact. Expiry defaults to {DEFAULT_EXPIRY_DAYS} days and can be set
          anywhere from {MIN_EXPIRY_DAYS} to {MAX_EXPIRY_DAYS} days — never indefinite.
        </p>

        <div className="mt-4 grid gap-4 sm:grid-cols-2">
          <div className="sm:col-span-2">
            <FormField label="Client" htmlFor="al-client" required>
              <Select
                id="al-client"
                value={clientId ?? ""}
                onChange={(e) => setClientId(Number(e.target.value) || null)}
              >
                <option value="">Choose client…</option>
                {(clients.data ?? []).map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </Select>
            </FormField>
          </div>
          <FormField label="Contact name" htmlFor="al-name" hint="Optional — for your records">
            <Input
              id="al-name"
              value={contactName}
              onChange={(e) => setContactName(e.target.value)}
              placeholder="e.g. Priya Menon"
            />
          </FormField>
          <FormField label="Contact email" htmlFor="al-email" hint="Optional — not emailed by DijiOne">
            <Input
              id="al-email"
              type="email"
              value={contactEmail}
              onChange={(e) => setContactEmail(e.target.value)}
              placeholder="name@client.com"
            />
          </FormField>
          <FormField label="Expires on" htmlFor="al-expiry">
            <Input
              id="al-expiry"
              type="date"
              value={expiryDate}
              min={minSelectableDate()}
              max={maxSelectableDate()}
              onChange={(e) => e.target.value && setExpiryDate(e.target.value)}
            />
          </FormField>
        </div>

        <div className="mt-5 flex items-center justify-end gap-3">
          {create.isError && (
            <p className="text-xs text-dt-danger">
              Could not generate a link. Check the client selection and try again.
            </p>
          )}
          <Button disabled={!clientId || create.isPending} onClick={() => create.mutate()}>
            {create.isPending ? "Generating…" : "Generate access link"}
          </Button>
        </div>
      </Card>

      {grants.isLoading ? (
        <LoadingState label="Loading access links…" />
      ) : grants.isError || !grants.data ? (
        <ErrorState onRetry={() => grants.refetch()} />
      ) : grants.data.length === 0 ? (
        <EmptyState
          title="No access links yet"
          description="Generate one above to give a client read-only visibility into their engagement."
        />
      ) : (
        <div className="overflow-x-auto">
          <Table>
            <Thead>
              <Tr>
                <Th>Client</Th>
                <Th>Contact</Th>
                <Th>Link</Th>
                <Th>Status</Th>
                <Th>Expires</Th>
                <Th>Redeemed</Th>
                <Th>Last used</Th>
                <Th>Uses</Th>
                <Th>Actions</Th>
              </Tr>
            </Thead>
            <tbody>
              {grants.data.map((g) => (
                <Tr key={g.public_id}>
                  <Td>
                    <div className="font-medium text-dt-text-primary">{g.client_name}</div>
                    <div className="text-xs text-dt-text-secondary">Issued {fmt(g.issued_at)}</div>
                  </Td>
                  <Td>
                    {g.contact_name || g.contact_email ? (
                      <div className="text-sm">
                        <div>{g.contact_name || "—"}</div>
                        <div className="text-xs text-dt-text-secondary">{g.contact_email}</div>
                      </div>
                    ) : (
                      "—"
                    )}
                  </Td>
                  <Td>
                    <code className="text-xs text-dt-text-secondary">{g.token_prefix}…</code>
                  </Td>
                  <Td>
                    <StatusBadge status={g.status} />
                  </Td>
                  <Td>
                    <ExpiryHint status={g.status} expiresAt={g.expires_at} />
                  </Td>
                  <Td>{fmt(g.redeemed_at)}</Td>
                  <Td>{fmt(g.last_used_at)}</Td>
                  <Td>{g.use_count}</Td>
                  <Td>
                    {g.status === "REVOKED" ? (
                      <span className="text-xs text-dt-text-secondary">Revoked {fmt(g.revoked_at)}</span>
                    ) : extendingId === g.public_id ? (
                      <div className="flex items-center gap-2">
                        <Input
                          type="date"
                          value={extendDate}
                          min={minSelectableDate()}
                          max={maxSelectableDate()}
                          onChange={(e) => setExtendDate(e.target.value)}
                          className="w-36 py-1.5 text-xs"
                        />
                        <Button
                          size="sm"
                          disabled={!extendDate || extend.isPending}
                          onClick={() =>
                            extendDate &&
                            extend.mutate({ publicId: g.public_id, expiresAt: endOfDayIso(extendDate) })
                          }
                        >
                          Save
                        </Button>
                        <Button size="sm" variant="ghost" onClick={() => setExtendingId(null)}>
                          Cancel
                        </Button>
                      </div>
                    ) : (
                      <div className="flex flex-wrap gap-2">
                        <Button
                          size="sm"
                          variant="secondary"
                          onClick={() => {
                            setExtendingId(g.public_id);
                            setExtendDate(dateInputValue(DEFAULT_EXPIRY_DAYS));
                          }}
                        >
                          Extend
                        </Button>
                        <Button
                          size="sm"
                          variant="secondary"
                          disabled={regenerate.isPending}
                          onClick={() => regenerate.mutate(g.public_id)}
                        >
                          Regenerate
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          disabled={revoke.isPending}
                          onClick={() => revoke.mutate(g.public_id)}
                        >
                          Revoke
                        </Button>
                      </div>
                    )}
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
