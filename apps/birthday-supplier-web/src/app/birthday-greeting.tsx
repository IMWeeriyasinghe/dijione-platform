import type { SupplierOrderDetailView } from "@dijione/contracts";

/** The birthday message P&C wrote for this order — read-only for suppliers.
 * Rendered as text (never HTML) with the author's line breaks preserved;
 * renders nothing when there is no greeting. */
export function BirthdayGreeting({ order }: { order: Pick<SupplierOrderDetailView, "birthday_greeting"> }) {
  const text = order.birthday_greeting?.trim();
  if (!text) return null;
  return (
    <div data-testid="birthday-greeting">
      <span className="text-xs font-medium uppercase tracking-wide text-dt-text-secondary">Birthday Greeting</span>
      <p className="mt-1 whitespace-pre-wrap text-sm text-dt-text-primary">{text}</p>
    </div>
  );
}
