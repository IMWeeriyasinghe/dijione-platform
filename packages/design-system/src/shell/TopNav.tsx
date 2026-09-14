"use client";

import { Home, Menu, Search, Sparkles } from "lucide-react";
import { NotificationsPanel } from "./NotificationsPanel";
import { UserMenu } from "./UserMenu";

export function TopNav({
  title,
  onMenuClick,
}: {
  title?: string;
  /** Renders a hamburger button (≤767px only) that opens AppShell's mobile
   * nav drawer. Omitted where TopNav is used without a companion Sidebar. */
  onMenuClick?: () => void;
}) {
  return (
    <header className="sticky top-0 z-30 flex h-16 shrink-0 items-center gap-4 border-b border-dt-border bg-dt-surface/90 px-4 backdrop-blur sm:px-6">
      {onMenuClick && (
        <button
          type="button"
          onClick={onMenuClick}
          aria-label="Open navigation menu"
          className="flex shrink-0 items-center justify-center rounded-full border border-dt-border bg-dt-surface-warm p-2 text-dt-text-secondary transition hover:border-dt-burnt-orange hover:text-dt-burnt-orange md:hidden"
        >
          <Menu className="size-4" />
        </button>
      )}
      {/* Left: DijiOne Home + fixed title. A plain <a>, not next/link — this
          leaves the current module's Next.js zone entirely (back to the
          shell root), so it must never carry a module basePath. */}
      <a
        href="/"
        title="DijiOne Home"
        className="flex shrink-0 items-center gap-1.5 rounded-full border border-dt-border bg-dt-surface-warm px-3 py-1.5 text-xs font-medium text-dt-text-secondary transition hover:border-dt-burnt-orange hover:text-dt-burnt-orange"
      >
        <Home className="size-3.5" />
        <span className="hidden sm:inline">DijiOne Home</span>
      </a>
      {title && <h2 className="hidden shrink-0 text-sm font-semibold text-dt-text-primary sm:block">{title}</h2>}

      {/* Center: flexible search area, grows to fill remaining space */}
      <div className="relative flex max-w-sm flex-1 items-center">
        <Search className="pointer-events-none absolute left-3 size-4 text-dt-text-secondary" />
        <input
          type="search"
          placeholder="Search DijiOne…"
          className="w-full rounded-full border border-dt-border bg-dt-surface-warm py-2 pl-9 pr-3 text-sm placeholder:text-dt-text-secondary focus:border-dt-orange focus:outline-none focus:ring-2 focus:ring-dt-orange/20"
        />
      </div>

      {/* Right: fixed action cluster, pinned to the far right */}
      <div className="ml-auto flex shrink-0 items-center gap-2 sm:gap-3">
        <button
          className="hidden items-center gap-1.5 rounded-full border border-dt-orange/30 bg-linear-to-r from-dt-red/10 to-dt-orange/10 px-3 py-1.5 text-xs font-medium text-dt-burnt-orange transition hover:from-dt-red/15 hover:to-dt-orange/15 sm:flex"
          title="Ask DijiOne — Copilot orchestration is planned for a future release"
        >
          <Sparkles className="size-3.5" />
          Ask DijiOne
        </button>
        <NotificationsPanel />
        <UserMenu />
      </div>
    </header>
  );
}
