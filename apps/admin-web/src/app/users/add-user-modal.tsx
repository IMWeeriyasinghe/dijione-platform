"use client";

import { useEffect, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { Search } from "lucide-react";
import type { DirectoryUserOut } from "@dijione/contracts";
import { Button, FormField, Input, Modal } from "@dijione/design-system";
import { ApiError, addUserFromDirectory, createAdminUser, directoryPhotoPath, searchDirectory } from "@/lib/api";
import { EmployeeAvatar, EmployeeRecordBadge } from "./identity";

function useDebounced(value: string, ms = 300): string {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return debounced;
}

function DirectoryResult({ person, onSelect }: { person: DirectoryUserOut; onSelect: () => void }) {
  return (
    <li className="flex items-center gap-3 rounded-xl border border-dt-border p-3" data-testid="directory-result">
      <EmployeeAvatar path={directoryPhotoPath(person.entra_object_id)} name={person.full_name} size={36} />
      <div className="min-w-0 flex-1">
        <p className="truncate font-medium text-dt-text-primary">{person.full_name}</p>
        <p className="truncate text-xs text-dt-text-secondary">{person.email}</p>
        <p className="truncate text-xs text-dt-text-secondary">
          {[person.job_title, person.department, person.employee_number ? `Employee No. ${person.employee_number}` : null]
            .filter(Boolean)
            .join(" · ")}
        </p>
        <div className="mt-1">
          <EmployeeRecordBadge status={person.employee_record} />
        </div>
      </div>
      {person.existing_user_id ? (
        <Link href={`/users/${person.existing_user_id}`} className="text-sm font-medium text-dt-burnt-orange">
          Already in DijiOne · Open profile
        </Link>
      ) : (
        <Button size="sm" variant="secondary" onClick={onSelect}>
          Select
        </Button>
      )}
    </li>
  );
}

/** Adds an employee before their first sign-in. Directory search comes first: the profile is filled
 * from Microsoft Entra and re-validated by the server. Manual entry is the controlled fallback and
 * leaves the profile awaiting directory verification. */
export function AddUserModal({ open, onClose, onCreated }: { open: boolean; onClose: () => void; onCreated: (id: number) => void }) {
  const [mode, setMode] = useState<"directory" | "manual">("directory");
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<DirectoryUserOut | null>(null);
  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [title, setTitle] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [existingId, setExistingId] = useState<number | null>(null);
  const term = useDebounced(query.trim());

  const results = useQuery({
    queryKey: ["admin", "directory", term],
    queryFn: () => searchDirectory(term),
    enabled: open && mode === "directory" && term.length >= 2,
    staleTime: 30_000,
  });

  const reset = () => {
    setMode("directory");
    setQuery("");
    setSelected(null);
    setEmail("");
    setFullName("");
    setTitle("");
    setError(null);
    setExistingId(null);
  };
  const close = () => {
    reset();
    onClose();
  };
  const done = (id: number) => {
    reset();
    onClose();
    onCreated(id);
  };
  const failed = (e: unknown, fallback: string) => {
    setError(e instanceof ApiError ? e.message : fallback);
    const existing = e instanceof ApiError ? e.body?.existing_user_id : undefined;
    setExistingId(typeof existing === "number" ? existing : null);
  };

  const fromDirectory = useMutation({
    mutationFn: (person: DirectoryUserOut) => addUserFromDirectory(person.entra_object_id),
    onSuccess: (created) => done(created.id),
    onError: (e) => failed(e, "Could not add this employee."),
  });
  const manual = useMutation({
    mutationFn: () => createAdminUser({ email: email.trim(), full_name: fullName.trim(), title: title.trim() || undefined }),
    onSuccess: (created) => done(created.id),
    onError: (e) => failed(e, "Could not add this user."),
  });

  return (
    <Modal open={open} onClose={close} title="Add User">
      <div className="flex flex-col gap-4">
        {mode === "directory" && !selected && (
          <>
            <p className="text-sm text-dt-text-secondary">
              Find the employee in the Microsoft Entra directory. Their details are filled in from the directory, and their
              access can be configured and previewed before their first sign-in.
            </p>
            <FormField label="Search the directory" htmlFor="add-user-search">
              <div className="relative">
                <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-dt-text-secondary" />
                <Input
                  id="add-user-search"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Name, work email or employee number"
                  className="pl-9"
                  autoFocus
                />
              </div>
            </FormField>
            {term.length >= 2 && results.isLoading && <p className="text-sm text-dt-text-secondary">Searching…</p>}
            {results.isError && (
              <p className="text-sm text-dt-danger">
                {results.error instanceof ApiError ? results.error.message : "The directory could not be searched."}
              </p>
            )}
            {results.data && results.data.length === 0 && <p className="text-sm text-dt-text-secondary">No matching employees.</p>}
            {results.data && results.data.length > 0 && (
              <ul className="flex max-h-80 flex-col gap-2 overflow-y-auto" aria-label="Directory results">
                {results.data.map((p) => (
                  <DirectoryResult key={p.entra_object_id} person={p} onSelect={() => setSelected(p)} />
                ))}
              </ul>
            )}
            <button type="button" className="self-start text-sm text-dt-burnt-orange underline" onClick={() => setMode("manual")}>
              Enter manually instead
            </button>
          </>
        )}

        {mode === "directory" && selected && (
          <div className="flex flex-col gap-3" data-testid="directory-selection">
            <div className="flex items-center gap-3">
              <EmployeeAvatar path={directoryPhotoPath(selected.entra_object_id)} name={selected.full_name} size={44} />
              <div className="min-w-0">
                <p className="font-semibold text-dt-text-primary">{selected.full_name}</p>
                <p className="text-sm text-dt-text-secondary">{selected.email}</p>
              </div>
            </div>
            <dl className="grid grid-cols-2 gap-2 text-sm">
              <dt className="text-dt-text-secondary">Job title</dt>
              <dd>{selected.job_title ?? "—"}</dd>
              <dt className="text-dt-text-secondary">Department</dt>
              <dd>{selected.department ?? "—"}</dd>
              <dt className="text-dt-text-secondary">Employee number</dt>
              <dd>{selected.employee_number ?? "—"}</dd>
              <dt className="text-dt-text-secondary">Employee record</dt>
              <dd>
                <EmployeeRecordBadge status={selected.employee_record} />
              </dd>
            </dl>
            {selected.employee_record !== "MATCHED" && (
              <p className="text-xs text-dt-text-secondary">
                Not matched to a BambooHR employee record: the profile can be created and configured, but default employee
                access and View as stay off until HR records are reconciled.
              </p>
            )}
          </div>
        )}

        {mode === "manual" && (
          <>
            <p className="text-sm text-dt-text-secondary">
              Manual entry is for cases the directory search cannot cover. The profile stays awaiting directory verification
              (no default access and no View as) until it is verified on the user&apos;s page or the person signs in.
            </p>
            <FormField label="Work email" htmlFor="add-user-email" required>
              <Input id="add-user-email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
            </FormField>
            <FormField label="Full name" htmlFor="add-user-name" required>
              <Input id="add-user-name" value={fullName} onChange={(e) => setFullName(e.target.value)} />
            </FormField>
            <FormField label="Job title" htmlFor="add-user-title">
              <Input id="add-user-title" value={title} onChange={(e) => setTitle(e.target.value)} />
            </FormField>
          </>
        )}

        {error && (
          <p className="text-sm text-dt-danger">
            {error}{" "}
            {existingId && (
              <Link href={`/users/${existingId}`} className="font-medium underline">
                Open profile
              </Link>
            )}
          </p>
        )}
        <div className="flex justify-end gap-2">
          {(selected || mode === "manual") && (
            <Button
              variant="secondary"
              onClick={() => {
                setSelected(null);
                setMode("directory");
                setError(null);
              }}
            >
              Back to search
            </Button>
          )}
          <Button variant="secondary" onClick={close}>
            Cancel
          </Button>
          {selected && (
            <Button onClick={() => fromDirectory.mutate(selected)} loading={fromDirectory.isPending}>
              Add User
            </Button>
          )}
          {mode === "manual" && (
            <Button onClick={() => manual.mutate()} loading={manual.isPending} disabled={!email.trim() || !fullName.trim()}>
              Add User
            </Button>
          )}
        </div>
      </div>
    </Modal>
  );
}
