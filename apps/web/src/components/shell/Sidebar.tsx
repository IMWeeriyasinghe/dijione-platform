"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

export type NavItem = {
  label: string;
  href: string;
  icon: LucideIcon;
  exact?: boolean;
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
}: {
  eyebrow?: string;
  title: string;
  sections: NavSection[];
  footer?: React.ReactNode;
}) {
  const pathname = usePathname();

  return (
    <aside className="flex h-full w-64 shrink-0 flex-col bg-linear-to-b from-dt-red-deep via-dt-red to-dt-burnt-orange text-white">
      <div className="flex items-center gap-2.5 px-5 pb-5 pt-6">
        <div className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-white/15 p-1.5">
          <Image src="/brand/dijital-team-logo.png" alt="" width={28} height={28} className="h-auto w-full object-contain" />
        </div>
        <div className="min-w-0">
          {eyebrow && <p className="truncate text-[11px] font-medium uppercase tracking-wide text-white/70">{eyebrow}</p>}
          <p className="truncate text-base font-semibold leading-tight">{title}</p>
        </div>
      </div>

      <nav className="dt-scrollbar flex-1 space-y-5 overflow-y-auto px-3 pb-4">
        {sections.map((section, i) => (
          <div key={section.label ?? i}>
            {section.label && (
              <p className="mb-1.5 px-3 text-[11px] font-semibold uppercase tracking-wide text-white/50">
                {section.label}
              </p>
            )}
            <div className="space-y-0.5">
              {section.items.map((item) => {
                const active = item.exact ? pathname === item.href : pathname.startsWith(item.href);
                const Icon = item.icon;
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    className={cn(
                      "flex items-center gap-2.5 rounded-xl px-3 py-2 text-sm font-medium transition",
                      active ? "bg-dt-cream text-dt-red-deep shadow-sm" : "text-white/85 hover:bg-white/10"
                    )}
                  >
                    <Icon className="size-4 shrink-0" />
                    <span className="truncate">{item.label}</span>
                  </Link>
                );
              })}
            </div>
          </div>
        ))}
      </nav>

      {footer && <div className="border-t border-white/15 px-4 py-4">{footer}</div>}
    </aside>
  );
}
