import type { NavSection } from "./Sidebar";
import { Sidebar } from "./Sidebar";
import { TopNav } from "./TopNav";

export function AppShell({
  eyebrow,
  title,
  sections,
  footer,
  topNavTitle,
  children,
}: {
  eyebrow?: string;
  title: string;
  sections: NavSection[];
  footer?: React.ReactNode;
  topNavTitle?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex min-h-screen">
      <Sidebar eyebrow={eyebrow} title={title} sections={sections} footer={footer} />
      <div className="flex min-w-0 flex-1 flex-col">
        <TopNav title={topNavTitle} />
        <main className="dt-scrollbar min-w-0 flex-1 overflow-y-auto px-4 py-6 sm:px-6 lg:px-8">
          {children}
        </main>
      </div>
    </div>
  );
}
