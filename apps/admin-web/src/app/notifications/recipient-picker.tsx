"use client";

import { useQuery } from "@tanstack/react-query";
import { useEffect, useId, useRef, useState } from "react";
import { Search, X } from "lucide-react";
import { searchNotificationRecipients, userPhotoPath, type NotificationRecipient } from "@/lib/api";
import { EmployeeAvatar } from "../users/identity";

const MIN_CHARS = 2;
const DEBOUNCE_MS = 300;

function useDebounced<T>(value: T, ms: number): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

/**
 * History Recipient filter: type a name, email or employee number and pick a DijiOne user, or
 * press Enter to search history for whatever was typed (deleted users, service accounts…).
 * Strictly a search box — it never adds a test recipient and never sends anything.
 */
export function RecipientPicker({ value, onChange }: { value: string; onChange: (email: string | undefined) => void }) {
  const [text, setText] = useState(value);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const listId = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  // Follow outside changes (Reset filters) without an effect: adjust state while rendering.
  const [prevValue, setPrevValue] = useState(value);
  if (value !== prevValue) {
    setPrevValue(value);
    setText(value);
  }

  const term = useDebounced(text.trim(), DEBOUNCE_MS);
  const enabled = open && term.length >= MIN_CHARS && term !== value;
  const search = useQuery({
    queryKey: ["admin", "notifications", "recipient-search", term],
    queryFn: ({ signal }) => searchNotificationRecipients(term, signal),
    enabled,
    staleTime: 30_000,
  });
  // Results always belong to the current term (the query is keyed by it), so an older, slower
  // response can never replace a newer one.
  const people: NotificationRecipient[] = enabled && search.data ? search.data : [];
  const typed = text.trim();
  const options: { key: string; email: string; person?: NotificationRecipient }[] = [
    ...people.map((p) => ({ key: `${p.source}:${p.user_id ?? p.email}`, email: p.email, person: p })),
    ...(typed.length > 0 ? [{ key: "manual", email: typed }] : []),
  ];
  const showList = open && typed.length > 0 && typed !== value;

  const choose = (email: string) => {
    setText(email);
    setOpen(false);
    onChange(email || undefined);
  };
  const clear = () => {
    setText("");
    setOpen(false);
    onChange(undefined);
    inputRef.current?.focus();
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setOpen(true);
      setActive((i) => Math.min(i + 1, Math.max(options.length - 1, 0)));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      const pick = showList ? options[active] : undefined;
      choose(pick ? pick.email : typed);
    } else if (e.key === "Escape") {
      if (open) {
        e.stopPropagation(); // close the suggestions, not a surrounding dialog
        setOpen(false);
      }
    }
  };

  return (
    <div className="relative">
      <div className="relative">
        <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-dt-text-secondary" aria-hidden />
        <input
          ref={inputRef}
          id="f-recipient"
          role="combobox"
          aria-expanded={showList}
          aria-controls={listId}
          aria-autocomplete="list"
          aria-activedescendant={showList && options[active] ? `${listId}-${active}` : undefined}
          aria-describedby={`${listId}-hint`}
          autoComplete="off"
          value={text}
          placeholder="Name, email or employee no."
          onChange={(e) => {
            setText(e.target.value);
            setOpen(true);
            setActive(0);
          }}
          onFocus={() => setOpen(true)}
          onBlur={() => setTimeout(() => setOpen(false), 150)}
          onKeyDown={onKeyDown}
          className="h-10 w-full rounded-md border border-dt-border bg-dt-surface pl-8 pr-8 text-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-dt-orange"
        />
        {(text || value) && (
          <button
            type="button"
            aria-label="Clear recipient"
            onClick={clear}
            className="absolute right-1.5 top-1/2 -translate-y-1/2 rounded p-1 text-dt-text-secondary hover:text-dt-text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-dt-orange"
          >
            <X className="h-4 w-4" aria-hidden />
          </button>
        )}
      </div>
      <span id={`${listId}-hint`} className="sr-only">
        Type at least two characters for suggestions. Press Enter to search history for exactly what you typed.
      </span>
      {showList && (
        <ul
          id={listId}
          role="listbox"
          aria-label="Recipient suggestions"
          aria-busy={search.isFetching}
          className="absolute z-20 mt-1 max-h-80 w-full min-w-[16rem] overflow-auto rounded-md border border-dt-border bg-dt-surface py-1 shadow-lg"
        >
          {enabled && search.isFetching && people.length === 0 && (
            <li className="px-3 py-2 text-sm text-dt-text-secondary" aria-live="polite">Searching…</li>
          )}
          {enabled && search.isError && (
            <li className="px-3 py-2 text-sm text-dt-danger" aria-live="polite">Could not search people.</li>
          )}
          {enabled && search.isSuccess && people.length === 0 && (
            <li className="px-3 py-2 text-sm text-dt-text-secondary" aria-live="polite">No matching people.</li>
          )}
          {options.map((o, i) => (
            <li
              key={o.key}
              id={`${listId}-${i}`}
              role="option"
              aria-selected={i === active}
              onMouseDown={(e) => {
                e.preventDefault();
                choose(o.email);
              }}
              onMouseEnter={() => setActive(i)}
              className={`flex cursor-pointer items-center gap-2 px-3 py-2 text-sm ${i === active ? "bg-dt-cream" : ""}`}
            >
              {o.person ? (
                <>
                  {o.person.source === "user" ? (
                    <EmployeeAvatar
                      path={o.person.has_photo && o.person.user_id ? userPhotoPath(o.person.user_id) : null}
                      name={o.person.full_name || o.person.email}
                      size={28}
                    />
                  ) : null}
                  <span className="min-w-0 flex-1">
                    <span className="block truncate font-medium">{o.person.full_name || o.person.email}</span>
                    {o.person.full_name && <span className="block truncate text-xs text-dt-text-secondary">{o.person.email}</span>}
                  </span>
                  {o.person.source === "history" && <span className="shrink-0 text-xs text-dt-text-secondary">History</span>}
                  {o.person.source === "user" && o.person.is_active === false && (
                    <span className="shrink-0 text-xs text-dt-text-secondary">Inactive</span>
                  )}
                </>
              ) : (
                <span className="min-w-0 flex-1 truncate">
                  Search history for “<strong>{o.email}</strong>”
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
