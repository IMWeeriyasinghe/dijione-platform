import { cn } from "@/lib/utils";

export function Table({ children }: { children: React.ReactNode }) {
  return (
    <div className="dt-scrollbar overflow-x-auto rounded-2xl border border-dt-border bg-dt-surface">
      <table className="w-full min-w-[640px] border-collapse text-sm">{children}</table>
    </div>
  );
}

export function Thead({ children }: { children: React.ReactNode }) {
  return <thead className="border-b border-dt-border bg-dt-surface-warm">{children}</thead>;
}

export function Th({ className, ...props }: React.ThHTMLAttributes<HTMLTableCellElement>) {
  return (
    <th
      className={cn(
        "px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-dt-text-secondary",
        className
      )}
      {...props}
    />
  );
}

export function Td({ className, ...props }: React.TdHTMLAttributes<HTMLTableCellElement>) {
  return <td className={cn("px-4 py-3.5 align-middle text-dt-text-primary", className)} {...props} />;
}

export function Tr({ className, ...props }: React.HTMLAttributes<HTMLTableRowElement>) {
  return (
    <tr className={cn("border-b border-dt-border last:border-0 hover:bg-dt-surface-warm/60", className)} {...props} />
  );
}
