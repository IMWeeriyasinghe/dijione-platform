import { cn } from "@/lib/utils";

export function FormField({
  label,
  htmlFor,
  hint,
  required,
  children,
}: {
  label: string;
  htmlFor?: string;
  hint?: string;
  required?: boolean;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={htmlFor} className="text-sm font-medium text-dt-text-primary">
        {label} {required && <span className="text-dt-danger">*</span>}
      </label>
      {children}
      {hint && <p className="text-xs text-dt-text-secondary">{hint}</p>}
    </div>
  );
}

const fieldClasses =
  "w-full rounded-lg border border-dt-border bg-dt-surface px-3 py-2 text-sm text-dt-text-primary placeholder:text-dt-text-secondary/60 focus:border-dt-orange focus:outline-none focus:ring-2 focus:ring-dt-orange/20";

export function Input({ className, ...props }: React.InputHTMLAttributes<HTMLInputElement>) {
  return <input className={cn(fieldClasses, className)} {...props} />;
}

export function Textarea({ className, ...props }: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea className={cn(fieldClasses, "min-h-24 resize-y", className)} {...props} />;
}

export function Select({ className, ...props }: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return <select className={cn(fieldClasses, className)} {...props} />;
}
