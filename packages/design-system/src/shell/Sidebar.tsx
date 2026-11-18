"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { ChevronsLeft, ChevronsRight, X, type LucideIcon } from "lucide-react";
import { cn } from "../utils";

export type NavItem = {
  label: string;
  href: string;
  icon: LucideIcon;
  exact?: boolean;
  /** True when `href` leaves this app's own Next.js "zone" (e.g. shell-web
   * linking into admin-web or talent-web). next/link's client-side router
   * can't render another zone's app in place — it silently updates the URL
   * bar without changing the page — so cross-zone items render a plain
   * `<a>` to force a full navigation instead. */
  external?: boolean;
};

export type NavSection = {
  label?: string;
  items: NavItem[];
};

export function Sidebar({
  eyebrow,
  title,
  sections,
  footer,
  homeHref,
  onNavigate,
  onClose,
  collapsed = false,
  onToggleCollapsed,
}: {
  eyebrow?: string;
  title: string;
  sections: NavSection[];
  footer?: React.ReactNode;
  /** When set, the brand/logo block becomes a link back to DijiOne Home.
   * Always a plain `<a>` (never next/link): this leaves the current zone
   * entirely, same cross-zone rationale as NavItem.external. */
  homeHref?: string;
  /** Mobile nav drawer only: fires after any nav item / brand link is
   * clicked, so AppShell can close the drawer on navigation instead of
   * leaving it open over the newly-loaded page. */
  onNavigate?: () => void;
  /** Mobile nav drawer only: renders an explicit close (X) button when
   * set. Omitted for the persistent desktop sidebar, which has nothing to
   * close. */
  onClose?: () => void;
  /** Desktop only, opt-in (AppShell `collapsible`): icon-only rail. */
  collapsed?: boolean;
  /** Desktop only, opt-in: renders the collapse / expand control when set. */
  onToggleCollapsed?: () => void;
}) {
  const pathname = usePathname();
  const ToggleIcon = collapsed ? ChevronsRight : ChevronsLeft;
  const toggle = onToggleCollapsed && (
    <button
      type="button"
      onClick={onToggleCollapsed}
      aria-expanded={!collapsed}
      aria-label={collapsed ? "Expand navigation" : "Collapse navigation"}
      title={collapsed ? "Expand navigation" : "Collapse navigation"}
      className="flex shrink-0 items-center justify-center rounded-lg p-1.5 text-white/80 transition hover:bg-white/10 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/80"
    >
      <ToggleIcon className="size-5" aria-hidden />
    </button>
  );

  const brand = (
    <>
      <div className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-white/15 p-1.5">
        {/* unoptimized: next/image's optimizer mishandles basePath for
            local images when this app is reached through another zone's
            rewrite proxy (shell-web -> admin-web/talent-web) — a tiny
            static brand logo gains nothing from on-demand resizing. */}
        <Image
          src="/brand/dijital-team-logo.png"
          alt=""
          width={28}
          height={28}
          unoptimized
          className="h-auto w-full object-contain"
        />
      </div>
      <div className={cn("min-w-0", collapsed && "sr-only")}>
        {eyebrow && <p className="truncate text-[11px] font-medium uppercase tracking-wide text-white/70">{eyebrow}</p>}
        <p className="truncate text-base font-semibold leading-tight">{title}</p>
      </div>
    </>
  );

  return (
    <aside
      data-collapsed={collapsed || undefined}
      className={cn(
        "flex h-full shrink-0 flex-col bg-linear-to-b from-dt-red-deep via-dt-red to-dt-burnt-orange text-white",
        onToggleCollapsed && "transition-[width] duration-200 ease-out motion-reduce:transition-none",
        collapsed ? "w-16" : "w-64"
      )}
    >
      <div className={cn("flex items-center gap-2.5 pb-5 pt-6", collapsed ? "flex-col px-2" : "px-5")}>
        {homeHref ? (
          // eslint-disable-next-line @next/next/no-html-link-for-pages -- cross-zone escape, see NavItem.external
          <a
            href={homeHref}
            title="DijiOne Home"
            onClick={onNavigate}
            className={cn("flex min-w-0 items-center gap-2.5 transition hover:opacity-90", !collapsed && "flex-1")}
          >
            {brand}
          </a>
        ) : (
          <div className={cn("flex min-w-0 items-center gap-2.5", !collapsed && "flex-1")}>{brand}</div>
        )}
        {toggle}
        {onClose && (
          <button
            type="button"
            onClick={onClose}
            aria-label="Close navigation menu"
            className="flex shrink-0 items-center justify-center rounded-lg p-1.5 text-white/80 transition hover:bg-white/10 hover:text-white"
          >
            <X className="size-5" />
          </button>
        )}
      </div>

      <nav aria-label={title} className={cn("dt-scrollbar flex-1 space-y-5 overflow-y-auto pb-4", collapsed ? "px-2" : "px-3")}>
        {sections.map((section, i) => (
          <div key={section.label ?? i}>
            {section.label &&
              (collapsed ? (
                // Collapsed: a thin separator keeps the grouping; the name stays for screen readers.
                <p className="mx-2 mb-2 border-t border-white/20 pt-2">
                  <span className="sr-only">{section.label}</span>
                </p>
              ) : (
                <p className="mb-1.5 px-3 text-[11px] font-semibold uppercase tracking-wide text-white/50">
                  {section.label}
                </p>
              ))}
            <div className="space-y-0.5">
              {section.items.map((item) => {
                const active = item.exact ? pathname === item.href : pathname.startsWith(item.href);
                const Icon = item.icon;
                const className = cn(
                  "flex items-center rounded-xl py-2 text-sm font-medium transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/80",
                  collapsed ? "justify-center px-0" : "gap-2.5 px-3",
                  active ? "bg-dt-cream text-dt-red-deep shadow-sm" : "text-white/85 hover:bg-white/10"
                );
                const content = (
                  <>
                    <Icon className="size-4 shrink-0" aria-hidden={collapsed || undefined} />
                    <span className={collapsed ? "sr-only" : "truncate"}>{item.label}</span>
                  </>
                );
                const shared = {
                  onClick: onNavigate,
                  className,
                  "aria-current": active ? ("page" as const) : undefined,
                  title: collapsed ? item.label : undefined,
                };
                return item.external ? (
                  // eslint-disable-next-line @next/next/no-html-link-for-pages -- cross-zone, see NavItem.external
                  <a key={item.href} href={item.href} {...shared}>
                    {content}
                  </a>
                ) : (
                  <Link key={item.href} href={item.href} {...shared}>
                    {content}
                  </Link>
                );
              })}
            </div>
          </div>
        ))}
      </nav>

      {footer && !collapsed && <div className="border-t border-white/15 px-4 py-4">{footer}</div>}
    </aside>
  );
}
