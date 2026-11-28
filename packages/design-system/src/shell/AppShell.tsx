"use client";

import { useEffect, useLayoutEffect, useState } from "react";
import { cn } from "../utils";
import type { NavSection } from "./Sidebar";
import { Sidebar } from "./Sidebar";
import type { RoleContext } from "./RoleIndicator";
import { TopNav } from "./TopNav";

export function AppShell({
  eyebrow,
  title,
  sections,
  footer,
  topNavTitle,
  homeHref,
  roleContext,
  collapsible,
  topNavSearch,
  children,
}: {
  eyebrow?: string;
  title: string;
  sections: NavSection[];
  footer?: React.ReactNode;
  topNavTitle?: string;
  homeHref?: string;
  /** Header role indicator context ("platform" or the application's module key). */
  roleContext?: RoleContext;
  /** OPT-IN: a collapse / expand control on the desktop sidebar (icon-only
   * rail, preference remembered per browser under `storageKey`). Omitted =
   * the unchanged always-expanded sidebar. Never affects the mobile drawer. */
  collapsible?: { storageKey: string };
  /** OPT-IN: wires the TopNav center search input. Scoped to DijiOne Home;
   * omit in all other applications to preserve the existing visual placeholder. */
  topNavSearch?: { query: string; onSearch: (q: string) => void };
  children: React.ReactNode;
}) {
  const storageKey = collapsible?.storageKey;
  const [collapsed, setCollapsed] = useState(false);
  // Applied before paint after hydration (server render is always expanded).
  useLayoutEffect(() => {
    if (!storageKey) return;
    try {
      if (window.localStorage.getItem(storageKey) === "1") setCollapsed(true);
    } catch {
      /* storage unavailable: stay expanded */
    }
  }, [storageKey]);
  const toggleCollapsed = () => {
    setCollapsed((c) => {
      const next = !c;
      try {
        if (storageKey) window.localStorage.setItem(storageKey, next ? "1" : "0");
      } catch {
        /* preference just isn't remembered */
      }
      return next;
    });
  };
  // Responsive audit finding (post-hardening review): the sidebar was a
  // permanently-rendered fixed w-64 column with no mobile collapse — on a
  // 375-414px viewport it consumed the majority of the screen, leaving
  // every page's content squeezed into a sliver. Below md (768px) the
  // persistent sidebar is now replaced by this drawer, opened via TopNav's
  // hamburger button.
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const closeMobileNav = () => setMobileNavOpen(false);

  useEffect(() => {
    if (!mobileNavOpen) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && closeMobileNav();
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [mobileNavOpen]);

  return (
    <div className="flex min-h-screen print:block">
      {/* Desktop sidebar — persistent at md (768px) and up. */}
      <div className="hidden print:hidden md:flex">
        <Sidebar
          eyebrow={eyebrow}
          title={title}
          sections={sections}
          footer={footer}
          homeHref={homeHref}
          collapsed={Boolean(storageKey) && collapsed}
          onToggleCollapsed={storageKey ? toggleCollapsed : undefined}
        />
      </div>

      {/* Mobile nav drawer — below md, opened via the hamburger in TopNav.
          Always mounted (not conditionally rendered) so the slide-in/out
          transition can play; visibility + interactivity are controlled by
          the transform/opacity/pointer-events classes below instead. */}
      <div
        className={cn("fixed inset-0 z-50 md:hidden print:hidden", mobileNavOpen ? "" : "pointer-events-none")}
        aria-hidden={!mobileNavOpen}
      >
        <div
          onClick={closeMobileNav}
          className={cn(
            "absolute inset-0 bg-black/40 transition-opacity duration-200",
            mobileNavOpen ? "opacity-100" : "opacity-0"
          )}
        />
        <div
          className={cn(
            "absolute inset-y-0 left-0 w-64 max-w-[85vw] transform transition-transform duration-200 ease-out motion-reduce:transition-none",
            mobileNavOpen ? "translate-x-0" : "-translate-x-full"
          )}
        >
          <Sidebar
            eyebrow={eyebrow}
            title={title}
            sections={sections}
            footer={footer}
            homeHref={homeHref}
            onNavigate={closeMobileNav}
            onClose={closeMobileNav}
          />
        </div>
      </div>

      <div className="flex min-w-0 flex-1 flex-col print:block">
        <div className="print:hidden">
          <TopNav title={topNavTitle} onMenuClick={() => setMobileNavOpen(true)} roleContext={roleContext} topNavSearch={topNavSearch} />
        </div>
        <main className="dt-scrollbar min-w-0 flex-1 overflow-y-auto px-4 py-6 sm:px-6 lg:px-8 print:overflow-visible print:p-0">
          {children}
        </main>
      </div>
    </div>
  );
}
