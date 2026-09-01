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
  listClientPortfolios,
  listMagicLinkGrants,
  regenerateMagicLinkGrant,
  revokeMagicLinkGrant,
} from "@/lib/api";

function fmt(value: string | null): string {
  if (!value) return "—";
  return new Date(value).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
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
    <Card className="mb-6 border-dt-orange/40 bg-dt-surface-warm">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <h3 className="text-sm font-semibold text-dt-text-primary">
            Access link for {grant.client_name}
          </h3>
          <p className="mt-1 text-xs text-dt-warning">
            Shown once. Copy it now — it cannot be retrieved again. Send it only to the intended
            client contact.
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
  const [freshLink, setFreshLink] = useState<MagicLinkGrantCreatedOut | null>(null);

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
      }),
    onSuccess: (grant) => {
      setFreshLink(grant);
      setContactName("");
      setContactEmail("");
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
      setFreshLink(grant);
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
        <OneTimeLinkPanel grant={freshLink} onDismiss={() => setFreshLink(null)} />
      )}

      <Card className="mb-6">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
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
          <div className="flex items-end">
            <Button
              disabled={!clientId || create.isPending}
              onClick={() => create.mutate()}
            >
              {create.isPending ? "Generating…" : "Generate access link"}
            </Button>
          </div>
        </div>
        {create.isError && (
          <p className="mt-3 text-xs text-dt-danger">
            Could not generate a link. Check the client selection and try again.
          </p>
        )}
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
                  <Td>{fmt(g.expires_at)}</Td>
                  <Td>{fmt(g.redeemed_at)}</Td>
                  <Td>{fmt(g.last_used_at)}</Td>
                  <Td>{g.use_count}</Td>
                  <Td>
                    {g.status === "REVOKED" ? (
                      <span className="text-xs text-dt-text-secondary">Revoked {fmt(g.revoked_at)}</span>
                    ) : (
                      <div className="flex gap-2">
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
