"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { listNotifications, markNotificationRead } from "@dijione/auth-client";
import { cn, formatDateTime } from "../utils";

export function NotificationsPanel() {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const queryClient = useQueryClient();

  const { data: notifications } = useQuery({
    queryKey: ["notifications"],
    queryFn: () => listNotifications(),
    refetchInterval: 30_000,
  });

  const unreadCount = notifications?.filter((n) => !n.is_read).length ?? 0;

  useEffect(() => {
    function onClickOutside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, []);

  async function handleMarkRead(id: number) {
    await markNotificationRead(id);
    queryClient.invalidateQueries({ queryKey: ["notifications"] });
  }

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen((o) => !o)}
        className="relative flex size-9 items-center justify-center rounded-full text-dt-text-secondary hover:bg-dt-surface-warm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-dt-orange"
        aria-label="Notifications"
      >
        <Bell className="size-4.5" />
        {unreadCount > 0 && (
          <span className="absolute -right-0.5 -top-0.5 flex size-4 items-center justify-center rounded-full bg-dt-danger text-[10px] font-bold text-white">
            {unreadCount > 9 ? "9+" : unreadCount}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 z-40 mt-2 w-80 rounded-2xl border border-dt-border bg-dt-surface p-2 shadow-xl">
          <div className="flex items-center justify-between px-2 py-1.5">
            <p className="text-sm font-semibold text-dt-text-primary">Notifications</p>
            {unreadCount > 0 && <span className="text-xs text-dt-text-secondary">{unreadCount} unread</span>}
          </div>
          <div className="dt-scrollbar max-h-80 overflow-y-auto">
            {!notifications || notifications.length === 0 ? (
              <p className="px-2 py-6 text-center text-sm text-dt-text-secondary">No notifications yet.</p>
            ) : (
              notifications.slice(0, 15).map((n) => (
                <button
                  key={n.id}
                  onClick={() => !n.is_read && handleMarkRead(n.id)}
                  className={cn(
                    "flex w-full flex-col gap-0.5 rounded-xl px-3 py-2.5 text-left transition hover:bg-dt-surface-warm",
                    !n.is_read && "bg-dt-cream/50"
                  )}
                >
                  <div className="flex items-center gap-2">
                    {!n.is_read && <span className="size-1.5 shrink-0 rounded-full bg-dt-orange" />}
                    <p className="truncate text-sm font-medium text-dt-text-primary">{n.title}</p>
                  </div>
                  {n.body && <p className="line-clamp-2 text-xs text-dt-text-secondary">{n.body}</p>}
                  <p className="text-[11px] text-dt-text-secondary/70">{formatDateTime(n.created_at)}</p>
                </button>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}
