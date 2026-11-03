"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Activity, AlertTriangle, CalendarDays, LayoutDashboard, Users } from "lucide-react";
import { cx } from "./kit";

const ITEMS = [
  { label: "Overview", href: "/", icon: LayoutDashboard, exact: true },
  { label: "Today", href: "/today", icon: CalendarDays },
  { label: "Activity", href: "/activity", icon: Activity },
  { label: "Employees", href: "/employees", icon: Users },
  { label: "Review", href: "/exceptions", icon: AlertTriangle },
];

/** Bottom navigation for the five operational pages on phones (below md).
 *  Administration stays in the shell's menu drawer (top-left button). */
export function MobileNav() {
  const pathname = usePathname() || "/";
  return (
    <nav aria-label="Diji On-site" className="fixed inset-x-0 bottom-0 z-40 border-t border-dt-border bg-dt-surface/95 pb-[env(safe-area-inset-bottom)] backdrop-blur md:hidden print:hidden">
      <ul className="grid grid-cols-5">
        {ITEMS.map(({ label, href, icon: Icon, exact }) => {
          const active = exact ? pathname === href : pathname === href || pathname.startsWith(`${href}/`);
          return (
            <li key={href}>
              <Link href={href} aria-current={active ? "page" : undefined}
                className={cx("flex min-h-14 flex-col items-center justify-center gap-0.5 text-[11px] font-medium focus-visible:bg-dt-surface-warm focus-visible:outline-none",
                  active ? "text-dt-red" : "text-dt-text-secondary")}>
                <Icon className="size-5" aria-hidden />
                {label}
                {active && <span aria-hidden className="mt-0.5 h-0.5 w-6 rounded-full bg-dt-red" />}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
