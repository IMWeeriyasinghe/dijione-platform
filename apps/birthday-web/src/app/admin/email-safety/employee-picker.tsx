"use client";

import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Button, FormField, Input } from "@dijione/design-system";
import { searchRecipientEmployees, type RecipientEmployee } from "@/lib/api";

function useDebounced(value: string, ms = 300) {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

/** Search active employees (People domain) and pick one to fill in the recipient's address and label.
 * Selecting someone only fills the form; the allowlist entry grants no application access. */
export function EmployeePicker({
  onSelect,
  onManual,
}: {
  onSelect: (employee: RecipientEmployee) => void;
  onManual: () => void;
}) {
  const [q, setQ] = useState("");
  const query = useDebounced(q.trim());
  const results = useQuery({
    queryKey: ["birthday-recipient-employee-search", query],
    queryFn: ({ signal }) => searchRecipientEmployees(query, signal),
    enabled: query.length >= 2,
    retry: false,
  });
  const items = results.data?.items ?? [];

  return (
    <div className="flex flex-col gap-2">
      <FormField label="Find an employee" htmlFor="recipient-search" hint="Name or email, at least 2 characters">
        <Input
          id="recipient-search"
          type="search"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="e.g. Nina or nina@dijitalteam.com"
          autoFocus
        />
      </FormField>
      <div aria-live="polite" className="flex flex-col gap-2">
        {query.length >= 2 && results.isFetching && <p className="text-sm text-dt-text-secondary">Searching…</p>}
        {results.isError && (
          <p role="alert" className="text-sm text-dt-danger">
            The employee directory is unavailable right now. Try again, or enter the address manually.
          </p>
        )}
        {results.isSuccess && items.length === 0 && (
          <p className="text-sm text-dt-text-secondary">No active employee matches. You can enter the address manually.</p>
        )}
        {items.map((e) => (
          <div key={e.email_address} className="flex items-center justify-between gap-3 rounded-xl border border-dt-border p-3">
            <div className="min-w-0">
              <p className="truncate font-medium text-dt-text-primary">{e.full_name}</p>
              <p className="truncate text-xs text-dt-text-secondary">
                {e.email_address}
                {e.department && ` · ${e.department}`}
              </p>
            </div>
            <Button size="sm" variant="secondary" disabled={e.already_recipient} onClick={() => onSelect(e)}>
              {e.already_recipient ? "Already added" : "Select"}
            </Button>
          </div>
        ))}
      </div>
      <button
        type="button"
        onClick={onManual}
        className="self-start text-sm font-medium text-dt-burnt-orange underline underline-offset-2"
      >
        Enter manually
      </button>
    </div>
  );
}
