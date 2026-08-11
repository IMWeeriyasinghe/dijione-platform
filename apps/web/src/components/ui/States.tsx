import { AlertTriangle, Inbox, Loader2, type LucideIcon } from "lucide-react";

export function LoadingState({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-16 text-dt-text-secondary">
      <Loader2 className="size-6 animate-spin text-dt-orange" />
      <p className="text-sm">{label}</p>
    </div>
  );
}

export function ErrorState({
  message = "Something went wrong. Please try again.",
  onRetry,
}: {
  message?: string;
  onRetry?: () => void;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-2xl border border-dt-danger/20 bg-[color-mix(in_srgb,var(--dt-danger)_6%,white)] py-16 text-center">
      <AlertTriangle className="size-6 text-dt-danger" />
      <p className="max-w-sm text-sm text-dt-text-primary">{message}</p>
      {onRetry && (
        <button
          onClick={onRetry}
          className="text-sm font-medium text-dt-burnt-orange underline underline-offset-2"
        >
          Try again
        </button>
      )}
    </div>
  );
}

export function EmptyState({
  title,
  description,
  icon: Icon = Inbox,
  action,
}: {
  title: string;
  description?: string;
  icon?: LucideIcon;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-2xl border border-dashed border-dt-border bg-dt-surface-warm py-16 text-center">
      <Icon className="size-7 text-dt-text-secondary/60" />
      <div>
        <p className="text-sm font-medium text-dt-text-primary">{title}</p>
        {description && <p className="mt-1 max-w-sm text-sm text-dt-text-secondary">{description}</p>}
      </div>
      {action}
    </div>
  );
}
