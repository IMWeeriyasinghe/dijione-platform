import type { SupplierOrderDetailView } from "@dijione/contracts";

function telHref(phone: string): string {
  return `tel:${phone.replace(/[^+0-9]/g, "")}`;
}

/** Delivery contact for the assigned supplier, from the order snapshot.
 * Shown only once the delivery details are verified (the API also withholds
 * the numbers until then). */
export function DeliveryContact({
  order,
}: {
  order: Pick<SupplierOrderDetailView, "address_verified" | "delivery_contact_phone" | "alternative_contact_phone">;
}) {
  return (
    <div data-testid="delivery-contact">
      <span className="text-xs font-medium uppercase tracking-wide text-dt-text-secondary">Delivery Contact</span>
      {!order.address_verified ? (
        <p className="mt-1 text-sm text-dt-text-secondary">
          Released once the delivery details have been verified by Dijital Team.
        </p>
      ) : order.delivery_contact_phone ? (
        <dl className="mt-1 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
          <dt className="text-dt-text-secondary">Contact number</dt>
          <dd className="text-dt-text-primary">
            <a href={telHref(order.delivery_contact_phone)} className="underline underline-offset-2">
              {order.delivery_contact_phone}
            </a>
          </dd>
          {order.alternative_contact_phone && (
            <>
              <dt className="text-dt-text-secondary">Alternative number</dt>
              <dd className="text-dt-text-primary">
                <a href={telHref(order.alternative_contact_phone)} className="underline underline-offset-2">
                  {order.alternative_contact_phone}
                </a>
              </dd>
            </>
          )}
        </dl>
      ) : (
        <p className="mt-1 text-sm text-dt-text-secondary">Contact number not available.</p>
      )}
    </div>
  );
}
