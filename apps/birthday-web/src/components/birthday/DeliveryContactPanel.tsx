"use client";

import { useState } from "react";
import { Button } from "@dijione/design-system";

type Choice = "mobile" | "home" | "other";

export type DeliveryContactOrder = {
  employee_mobile_phone?: string | null;
  employee_home_phone?: string | null;
  delivery_contact_phone?: string | null;
};

const PHONE = /^\+?[0-9][0-9 ()\-.]{4,40}$/;

function initialChoice(o: DeliveryContactOrder): Choice {
  if (o.delivery_contact_phone && o.delivery_contact_phone === o.employee_mobile_phone) return "mobile";
  if (o.delivery_contact_phone && o.delivery_contact_phone === o.employee_home_phone) return "home";
  if (o.delivery_contact_phone) return "other";
  return o.employee_mobile_phone ? "mobile" : o.employee_home_phone ? "home" : "other";
}

/** Team-member contact numbers from BambooHR (via People API) shown during
 * P&C verification, plus the number the supplier will be given. Choosing a
 * number is not an address correction and never flags the order. */
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
  const [choice, setChoice] = useState<Choice>(() => initialChoice(order));
  const [other, setOther] = useState(
    initialChoice(order) === "other" ? (order.delivery_contact_phone ?? "") : "",
  );

  const selected =
    choice === "mobile" ? order.employee_mobile_phone : choice === "home" ? order.employee_home_phone : other.trim();
  const valid = !selected || PHONE.test(selected);
  const changed = (selected || null) !== (order.delivery_contact_phone ?? null);

  return (
    <div className="mb-3 rounded-xl border border-dt-border p-3" data-testid="delivery-contact-panel">
      <p className="text-xs font-medium uppercase tracking-wide text-dt-text-secondary">Team member contact</p>
      <dl className="mt-1 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
        <dt className="text-dt-text-secondary">Mobile</dt>
        <dd className="text-dt-text-primary">{order.employee_mobile_phone || "Not in BambooHR"}</dd>
        <dt className="text-dt-text-secondary">Home Phone</dt>
        <dd className="text-dt-text-primary">{order.employee_home_phone || "Not in BambooHR"}</dd>
        <dt className="text-dt-text-secondary">Given to supplier</dt>
        <dd className="font-medium text-dt-text-primary" data-testid="delivery-contact-current">
          {order.delivery_contact_phone || "None"}
        </dd>
      </dl>

      {canEdit && (
        <fieldset className="mt-3">
          <legend className="text-xs text-dt-text-secondary">Delivery contact number for the supplier</legend>
          <div className="mt-1 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
            {order.employee_mobile_phone && (
              <label className="flex items-center gap-1">
                <input type="radio" name="delivery-contact" checked={choice === "mobile"} onChange={() => setChoice("mobile")} />
                Mobile
              </label>
            )}
            {order.employee_home_phone && (
              <label className="flex items-center gap-1">
                <input type="radio" name="delivery-contact" checked={choice === "home"} onChange={() => setChoice("home")} />
                Home Phone
              </label>
            )}
            <label className="flex items-center gap-1">
              <input type="radio" name="delivery-contact" checked={choice === "other"} onChange={() => setChoice("other")} />
              Other number
            </label>
            {choice === "other" && (
              <input
                aria-label="Other contact number"
                className="w-48 rounded-lg border border-dt-border px-2 py-1 text-sm"
                value={other}
                onChange={(e) => setOther(e.target.value)}
                placeholder="+94 77 123 4567"
              />
            )}
          </div>
          {!valid && (
            <p className="mt-1 text-xs text-dt-danger">Use digits, spaces, +, -, ( or ) only.</p>
          )}
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
