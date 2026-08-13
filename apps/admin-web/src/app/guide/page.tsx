"use client";

import { useEffect, useRef, useState } from "react";
import { Download } from "lucide-react";
import { Button, PageHeader } from "@dijione/design-system";
import { AccessModelDiagram } from "./AccessModelDiagram";
import { GUIDE_SECTIONS } from "./content";
import { GuideExportDialog } from "./GuideExportDialog";

function GuideTOC({ activeId }: { activeId: string }) {
  return (
    <nav className="flex flex-col gap-0.5">
      {GUIDE_SECTIONS.map((s) => (
        <a
          key={s.id}
          href={`#${s.id}`}
          className={`rounded-lg px-3 py-1.5 text-sm transition ${
            activeId === s.id
              ? "bg-dt-cream font-medium text-dt-burnt-orange"
              : "text-dt-text-secondary hover:bg-dt-surface-warm hover:text-dt-text-primary"
          }`}
        >
          {s.title}
        </a>
      ))}
    </nav>
  );
}

export default function AdminGuidePage() {
  const [activeId, setActiveId] = useState(GUIDE_SECTIONS[0].id);
  const [exportOpen, setExportOpen] = useState(false);
  const [printSelection, setPrintSelection] = useState<string[] | null>(null);
  const contentRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const headings = GUIDE_SECTIONS.map((s) => document.getElementById(s.id)).filter(Boolean) as HTMLElement[];
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries.filter((e) => e.isIntersecting).sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
        if (visible[0]) setActiveId(visible[0].target.id);
      },
      { rootMargin: "-96px 0px -70% 0px" }
    );
    headings.forEach((h) => observer.observe(h));
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (printSelection === null) return;
    const onAfterPrint = () => setPrintSelection(null);
    window.addEventListener("afterprint", onAfterPrint);
    const t = setTimeout(() => window.print(), 50);
    return () => {
      clearTimeout(t);
      window.removeEventListener("afterprint", onAfterPrint);
    };
  }, [printSelection]);

  const printSections = printSelection ? GUIDE_SECTIONS.filter((s) => printSelection.includes(s.id)) : [];
  const includeDiagramInPrint = printSelection?.includes("access-model") ?? false;

  return (
    <div>
      <div className="print:hidden">
        <PageHeader
          title="Guide & Access Model"
          description="How DijiOne authorization works, and how to perform common administrative tasks — without leaving the Admin Center."
          action={
            <Button size="sm" onClick={() => setExportOpen(true)}>
              <Download className="size-4" /> Download Guide
            </Button>
          }
        />

        <h2 className="mb-3 text-lg font-semibold text-dt-text-primary">DijiOne Access &amp; Authorization Model</h2>
        <div className="mb-8 rounded-2xl border border-dt-border bg-dt-surface-warm p-4 sm:p-6">
          <AccessModelDiagram />
        </div>

        {/* Mobile/tablet: collapsible "On this page" */}
        <details className="mb-6 rounded-xl border border-dt-border bg-dt-surface p-3 lg:hidden">
          <summary className="cursor-pointer text-sm font-semibold text-dt-text-primary">On this page</summary>
          <div className="mt-2">
            <GuideTOC activeId={activeId} />
          </div>
        </details>

        <div className="grid gap-8 lg:grid-cols-[220px_1fr]">
          <aside className="hidden lg:block">
            <div className="sticky top-20">
              <p className="mb-2 px-3 text-xs font-semibold uppercase tracking-wide text-dt-text-secondary">Contents</p>
              <GuideTOC activeId={activeId} />
            </div>
          </aside>

          <div ref={contentRef} className="flex max-w-3xl flex-col gap-10">
            {GUIDE_SECTIONS.map((s) => (
              <section key={s.id} id={s.id} className="scroll-mt-24">
                <h3 className="mb-3 text-base font-semibold text-dt-text-primary">{s.title}</h3>
                {s.body}
              </section>
            ))}
          </div>
        </div>
      </div>

      <GuideExportDialog
        open={exportOpen}
        onClose={() => setExportOpen(false)}
        sections={GUIDE_SECTIONS}
        onDownload={(ids) => {
          setExportOpen(false);
          setPrintSelection(ids);
        }}
      />

      {/* Print-only export surface: branded, chrome-free, only selected sections */}
      {printSelection !== null && (
        <div className="hidden print:block">
          <div className="mb-6 flex items-center justify-between border-b border-dt-border pb-4">
            <div>
              <p className="text-xl font-bold text-dt-text-primary">DijiOne Admin Center</p>
              <p className="text-sm text-dt-text-secondary">Guide &amp; Access Model</p>
            </div>
            <p className="text-xs text-dt-text-secondary">Generated {new Date().toLocaleDateString()}</p>
          </div>
          {includeDiagramInPrint && (
            <div className="mb-8 break-inside-avoid">
              <h3 className="mb-3 text-base font-semibold text-dt-text-primary">DijiOne Access &amp; Authorization Model</h3>
              <AccessModelDiagram />
            </div>
          )}
          <div className="flex flex-col gap-8">
            {printSections
              .filter((s) => s.id !== "access-model")
              .map((s) => (
                <section key={s.id} className="break-inside-avoid">
                  <h3 className="mb-3 text-base font-semibold text-dt-text-primary">{s.title}</h3>
                  {s.body}
                </section>
              ))}
          </div>
        </div>
      )}
    </div>
  );
}
