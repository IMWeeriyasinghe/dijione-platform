import type { NavSection } from "./Sidebar";
import { Sidebar } from "./Sidebar";
import { TopNav } from "./TopNav";

export function AppShell({
  eyebrow,
  title,
  sections,
  footer,
  topNavTitle,
  homeHref,
  children,
}: {
  eyebrow?: string;
  title: string;
  sections: NavSection[];
  footer?: React.ReactNode;
  topNavTitle?: string;
  homeHref?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex min-h-screen print:block">
      <div className="print:hidden">
        <Sidebar eyebrow={eyebrow} title={title} sections={sections} footer={footer} homeHref={homeHref} />
      </div>
      <div className="flex min-w-0 flex-1 flex-col print:block">
        <div className="print:hidden">
          <TopNav title={topNavTitle} />
        </div>
        <main className="dt-scrollbar min-w-0 flex-1 overflow-y-auto px-4 py-6 sm:px-6 lg:px-8 print:overflow-visible print:p-0">
          {children}
        </main>
      </div>
    </div>
  );
}
