"use client";

import { Search, Sparkles } from "lucide-react";
import { NotificationsPanel } from "./NotificationsPanel";
import { UserMenu } from "./UserMenu";

export function TopNav({ title }: { title?: string }) {
  return (
    <header className="sticky top-0 z-30 flex h-16 shrink-0 items-center gap-4 border-b border-dt-border bg-dt-surface/90 px-4 backdrop-blur sm:px-6">
      {title && <h2 className="hidden text-sm font-semibold text-dt-text-primary sm:block">{title}</h2>}
      <div className="relative ml-auto flex max-w-sm flex-1 items-center sm:ml-0">
        <Search className="pointer-events-none absolute left-3 size-4 text-dt-text-secondary" />
        <input
          type="search"
          placeholder="Search DijiOne…"
          className="w-full rounded-full border border-dt-border bg-dt-surface-warm py-2 pl-9 pr-3 text-sm placeholder:text-dt-text-secondary focus:border-dt-orange focus:outline-none focus:ring-2 focus:ring-dt-orange/20"
        />
      </div>
      <button
        className="hidden items-center gap-1.5 rounded-full border border-dt-orange/30 bg-linear-to-r from-dt-red/10 to-dt-orange/10 px-3 py-1.5 text-xs font-medium text-dt-burnt-orange transition hover:from-dt-red/15 hover:to-dt-orange/15 sm:flex"
        title="Ask DijiOne — Copilot orchestration is planned for a future release"
      >
        <Sparkles className="size-3.5" />
        Ask DijiOne
      </button>
      <NotificationsPanel />
      <UserMenu />
    </header>
  );
}
