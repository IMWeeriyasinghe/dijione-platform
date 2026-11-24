"use client";

import { useState } from "react";
import { Button } from "@dijione/design-system";

export type DeliveryContactOrder = {
  employee_mobile_phone?: string | null;
  employee_home_phone?: string | null;
  delivery_contact_phone?: string | null;
};

type Choice = "primary" | "secondary" | "other";

const PHONE = /^\+?[0-9][0-9 ()\-.]{4,40}$/;

/** Primary = the BambooHR Mobile Phone (the number Customer Portal also shows
 * as the team member's phone); when there is no mobile, the home number takes
 * its place. Secondary = the remaining number, only when there are two. */
export function contactNumbers(order: DeliveryContactOrder): { primary: string | null; secondary: string | null } {
  const mobile = order.employee_mobile_phone?.trim() || null;
  const home = order.employee_home_phone?.trim() || null;
  const primary = mobile ?? home;
  const secondary = mobile && home && home !== mobile ? home : null;
  return { primary, secondary };
}

function initialChoice(order: DeliveryContactOrder): Choice {
  const { primary, secondary } = contactNumbers(order);
  const current = order.delivery_contact_phone?.trim() || null;
  if (current && current === primary) return "primary";
  if (current && current === secondary) return "secondary";
  if (current) return "other";
  return primary ? "primary" : secondary ? "secondary" : "other";
}

/** Team-member contact numbers shown during P&C verification, plus the number
 * the supplier is given. Choosing it is not an address correction and never
 * flags the order or changes how Verify routes it. */
export function DeliveryContactPanel({
  order,
  canEdit,
  saving,
  onSave,
}: {
  order: DeliveryContactOrder;
  canEdit: boolean;
  saving?: boolean;
  onSave: (phone: string | null) => void;
}) {
  const { primary, secondary } = contactNumbers(order);
  const [choice, setChoice] = useState<Choice>(() => initialChoice(order));
  const [other, setOther] = useState(
    initialChoice(order) === "other" ? (order.delivery_contact_phone ?? "") : "",
  );

  const selected = choice === "primary" ? primary : choice === "secondary" ? secondary : other.trim();
  const valid = !selected || PHONE.test(selected);
  const changed = (selected || null) !== (order.delivery_contact_phone?.trim() || null);
  const hasOptions = !!primary || !!secondary;

  return (
    <div className="mb-3 rounded-xl border border-dt-border p-3" data-testid="delivery-contact-panel">
      <p className="text-xs font-medium uppercase tracking-wide text-dt-text-secondary">Team member contact</p>
      <dl className="mt-1 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
        <dt className="text-dt-text-secondary">Primary contact</dt>
        <dd className="text-dt-text-primary" data-testid="primary-contact">{primary ?? "Not available"}</dd>
        {secondary && (
          <>
            <dt className="text-dt-text-secondary">Secondary contact</dt>
            <dd className="text-dt-text-primary" data-testid="secondary-contact">{secondary}</dd>
          </>
        )}
        <dt className="text-dt-text-secondary">Supplier will see</dt>
        <dd className="font-medium text-dt-text-primary" data-testid="delivery-contact-current">
          {order.delivery_contact_phone || "No number"}
        </dd>
      </dl>

      {canEdit && (
        <fieldset className="mt-3">
          <legend className="text-xs text-dt-text-secondary">Delivery contact number for the supplier</legend>
          {hasOptions ? (
            <div className="mt-1 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
              {primary && (
                <label className="flex items-center gap-1">
                  <input type="radio" name="delivery-contact" checked={choice === "primary"} onChange={() => setChoice("primary")} />
                  Primary contact
                </label>
              )}
              {secondary && (
                <label className="flex items-center gap-1">
                  <input type="radio" name="delivery-contact" checked={choice === "secondary"} onChange={() => setChoice("secondary")} />
                  Secondary contact
                </label>
              )}
              <label className="flex items-center gap-1">
                <input type="radio" name="delivery-contact" checked={choice === "other"} onChange={() => setChoice("other")} />
                Other number
              </label>
            </div>
          ) : (
            <p className="mt-1 text-xs text-dt-text-secondary">No number on file — enter one for the supplier.</p>
          )}
          {choice === "other" && (
            <input
              aria-label="Other contact number"
              className="mt-2 w-56 rounded-lg border border-dt-border px-2 py-1 text-sm"
              value={other}
              onChange={(e) => setOther(e.target.value)}
              placeholder="+94 77 123 4567"
            />
          )}
          {!valid && <p className="mt-1 text-xs text-dt-danger">Use digits, spaces, +, -, ( or ) only.</p>}
          <Button
            size="sm"
            variant="secondary"
            className="mt-2"
            disabled={!changed || !valid}
            loading={saving}
            onClick={() => onSave(selected || null)}
          >
            Save contact
          </Button>
        </fieldset>
      )}
    </div>
  );
}
