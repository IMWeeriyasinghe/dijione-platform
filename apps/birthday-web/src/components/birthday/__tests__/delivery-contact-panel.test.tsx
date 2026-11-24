import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { ReactNode } from "react";

vi.mock("@dijione/design-system", () => ({
  Button: ({ children, onClick, disabled }: { children: ReactNode; onClick?: () => void; disabled?: boolean }) => (
    <button onClick={onClick} disabled={disabled}>{children}</button>
  ),
}));

import { contactNumbers, DeliveryContactPanel } from "../DeliveryContactPanel";

const BOTH = { employee_mobile_phone: "+94 77 111 2222", employee_home_phone: "+94 11 333 4444",
  delivery_contact_phone: "+94 77 111 2222" };

describe("contactNumbers", () => {
  it("primary is the mobile; secondary is the other number only when there are two", () => {
    expect(contactNumbers(BOTH)).toEqual({ primary: "+94 77 111 2222", secondary: "+94 11 333 4444" });
    expect(contactNumbers({ employee_mobile_phone: "+94 77 1", employee_home_phone: null }))
      .toEqual({ primary: "+94 77 1", secondary: null });
    expect(contactNumbers({ employee_mobile_phone: null, employee_home_phone: "+94 11 2" }))
      .toEqual({ primary: "+94 11 2", secondary: null }); // home takes the primary slot
    expect(contactNumbers({ employee_mobile_phone: "+94 77 1", employee_home_phone: "+94 77 1" }).secondary).toBeNull();
    expect(contactNumbers({})).toEqual({ primary: null, secondary: null });
  });
});

describe("DeliveryContactPanel", () => {
  it("shows primary and secondary contacts and what the supplier will see", () => {
    render(<DeliveryContactPanel order={BOTH} canEdit={false} onSave={() => {}} />);
    expect(screen.getByTestId("primary-contact")).toHaveTextContent("+94 77 111 2222");
    expect(screen.getByTestId("secondary-contact")).toHaveTextContent("+94 11 333 4444");
    expect(screen.getByTestId("delivery-contact-current")).toHaveTextContent("+94 77 111 2222");
    expect(screen.queryByText("Save contact")).toBeNull(); // read-only for non-admins
    expect(screen.queryByText("Mobile")).toBeNull();
    expect(screen.queryByText("Home Phone")).toBeNull();
  });

  it("lets P&C choose the secondary contact", () => {
    const onSave = vi.fn();
    render(<DeliveryContactPanel order={BOTH} canEdit onSave={onSave} />);
    expect(screen.getByText("Save contact")).toBeDisabled();
    fireEvent.click(screen.getByLabelText("Secondary contact"));
    fireEvent.click(screen.getByText("Save contact"));
    expect(onSave).toHaveBeenCalledWith("+94 11 333 4444");
  });

  it("offers only options that hold a value", () => {
    render(<DeliveryContactPanel order={{ employee_mobile_phone: "+94 77 555 6666", delivery_contact_phone: "+94 77 555 6666" }}
      canEdit onSave={() => {}} />);
    expect(screen.queryByTestId("secondary-contact")).toBeNull();
    expect(screen.getByLabelText("Primary contact")).toBeChecked();
    expect(screen.queryByLabelText("Secondary contact")).toBeNull();
    expect(screen.getByLabelText("Other number")).toBeInTheDocument();
  });

  it("accepts a valid other number and rejects an invalid one", () => {
    const onSave = vi.fn();
    render(<DeliveryContactPanel order={BOTH} canEdit onSave={onSave} />);
    fireEvent.click(screen.getByLabelText("Other number"));
    fireEvent.change(screen.getByLabelText("Other contact number"), { target: { value: "call me" } });
    expect(screen.getByText(/digits, spaces/)).toBeInTheDocument();
    expect(screen.getByText("Save contact")).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Other contact number"), { target: { value: "+94 71 999 0000" } });
    fireEvent.click(screen.getByText("Save contact"));
    expect(onSave).toHaveBeenCalledWith("+94 71 999 0000");
  });

  it("offers Refresh contact from People on a legacy order with no contact captured", () => {
    const onRefresh = vi.fn();
    render(<DeliveryContactPanel order={{}} canEdit refreshable onRefresh={onRefresh} onSave={() => {}} />);
    expect(screen.getByText("No contact captured when this order was created.")).toBeInTheDocument();
    fireEvent.click(screen.getByText("Refresh contact from People"));
    expect(onRefresh).toHaveBeenCalledTimes(1);
  });

  it("still offers the refresh when only one number is captured, without the legacy message", () => {
    render(
      <DeliveryContactPanel order={{ employee_mobile_phone: "+94 77 555 6666" }} canEdit refreshable
        onRefresh={() => {}} onSave={() => {}} />,
    );
    expect(screen.getByText("Refresh contact from People")).toBeInTheDocument();
    expect(screen.queryByText(/No contact captured/)).toBeNull();
  });

  it("hides the refresh when nothing is refreshable, for non-admins, and shows an error message", () => {
    const { rerender } = render(<DeliveryContactPanel order={BOTH} canEdit refreshable={false} onRefresh={() => {}} onSave={() => {}} />);
    expect(screen.queryByText("Refresh contact from People")).toBeNull();
    rerender(<DeliveryContactPanel order={{}} canEdit={false} refreshable onRefresh={() => {}} onSave={() => {}} />);
    expect(screen.queryByText("Refresh contact from People")).toBeNull();
    rerender(
      <DeliveryContactPanel order={{}} canEdit refreshable onRefresh={() => {}} onSave={() => {}}
        refreshError="No contact number is currently available from People." />,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("No contact number is currently available from People.");
  });

  it("with no numbers on file, goes straight to entering one", () => {
    const onSave = vi.fn();
    render(<DeliveryContactPanel order={{}} canEdit onSave={onSave} />);
    expect(screen.getByTestId("primary-contact")).toHaveTextContent("Not available");
    expect(screen.getByTestId("delivery-contact-current")).toHaveTextContent("No number");
    expect(screen.getByText(/No number on file/)).toBeInTheDocument();
    expect(screen.queryByLabelText("Primary contact")).toBeNull();
    fireEvent.change(screen.getByLabelText("Other contact number"), { target: { value: "+94 77 123 4567" } });
    fireEvent.click(screen.getByText("Save contact"));
    expect(onSave).toHaveBeenCalledWith("+94 77 123 4567");
  });
});
