import { cn } from "@/lib/utils";
import { Loader2 } from "lucide-react";
import { forwardRef } from "react";

type Variant = "primary" | "secondary" | "ghost" | "danger";
type Size = "sm" | "md";

const VARIANT_CLASSES: Record<Variant, string> = {
  primary:
    "bg-linear-to-r from-dt-red to-dt-orange text-white shadow-sm hover:brightness-105 focus-visible:ring-dt-orange disabled:opacity-50",
  secondary:
    "bg-dt-surface-warm text-dt-text-primary border border-dt-border hover:bg-dt-cream focus-visible:ring-dt-orange disabled:opacity-50",
  ghost: "text-dt-text-secondary hover:bg-dt-surface-warm focus-visible:ring-dt-orange disabled:opacity-50",
  danger: "bg-dt-danger text-white hover:brightness-105 focus-visible:ring-dt-danger disabled:opacity-50",
};

const SIZE_CLASSES: Record<Size, string> = {
  sm: "text-sm px-3 py-1.5 gap-1.5",
  md: "text-sm px-4 py-2 gap-2",
};

type ButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = "primary", size = "md", loading, disabled, children, ...props }, ref) => {
    return (
      <button
        ref={ref}
        disabled={disabled || loading}
        className={cn(
          "inline-flex items-center justify-center rounded-lg font-medium transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-1 disabled:cursor-not-allowed",
          VARIANT_CLASSES[variant],
          SIZE_CLASSES[size],
          className
        )}
        {...props}
      >
        {loading && <Loader2 className="size-4 animate-spin" />}
        {children}
      </button>
    );
  }
);
Button.displayName = "Button";
