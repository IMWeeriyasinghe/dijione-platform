"use client";

import { LogOut } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useAuth } from "@/lib/auth-context";
import { Avatar } from "@/components/ui/Avatar";

export function UserMenu() {
  const { user, logout } = useAuth();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function onClickOutside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, []);

  if (!user) return null;

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-2 rounded-full p-0.5 hover:bg-dt-surface-warm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-dt-orange"
      >
        <Avatar name={user.full_name} color={user.avatar_color} size={32} />
      </button>
      {open && (
        <div className="absolute right-0 z-40 mt-2 w-56 rounded-2xl border border-dt-border bg-dt-surface p-2 shadow-xl">
          <div className="px-3 py-2">
            <p className="truncate text-sm font-semibold text-dt-text-primary">{user.full_name}</p>
            <p className="truncate text-xs text-dt-text-secondary">{user.title ?? user.email}</p>
          </div>
          <div className="my-1 h-px bg-dt-border" />
          <button
            onClick={logout}
            className="flex w-full items-center gap-2 rounded-xl px-3 py-2 text-left text-sm text-dt-danger hover:bg-dt-surface-warm"
          >
            <LogOut className="size-4" />
            Switch persona
          </button>
        </div>
      )}
    </div>
  );
}
