import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { ReactNode } from "react";

vi.mock("@dijione/design-system", () => ({
  Button: ({ children, onClick, disabled }: { children: ReactNode; onClick?: () => void; disabled?: boolean }) => (
    <button onClick={onClick} disabled={disabled}>{children}</button>
  ),
}));

import { DeliveryContactPanel } from "../DeliveryContactPanel";

const ORDER = { employee_mobile_phone: "+94 77 111 2222", employee_home_phone: "+94 11 333 4444",
  delivery_contact_phone: "+94 77 111 2222" };

describe("DeliveryContactPanel", () => {
  it("shows both BambooHR numbers and the number given to the supplier", () => {
    render(<DeliveryContactPanel order={ORDER} canEdit={false} onSave={() => {}} />);
    expect(screen.getByText("Mobile")).toBeInTheDocument();
    expect(screen.getAllByText("+94 77 111 2222").length).toBeGreaterThan(0);
    expect(screen.getByText("+94 11 333 4444")).toBeInTheDocument();
    expect(screen.getByTestId("delivery-contact-current")).toHaveTextContent("+94 77 111 2222");
    expect(screen.queryByText("Save contact")).toBeNull(); // read-only for non-admins
  });

  it("lets P&C choose the home number", () => {
    const onSave = vi.fn();
    render(<DeliveryContactPanel order={ORDER} canEdit onSave={onSave} />);
    expect(screen.getByText("Save contact")).toBeDisabled();
    fireEvent.click(screen.getByLabelText("Home Phone"));
    fireEvent.click(screen.getByText("Save contact"));
    expect(onSave).toHaveBeenCalledWith("+94 11 333 4444");
  });

  it("accepts a valid other number and rejects an invalid one", () => {
    const onSave = vi.fn();
    render(<DeliveryContactPanel order={ORDER} canEdit onSave={onSave} />);
    fireEvent.click(screen.getByLabelText("Other number"));
    fireEvent.change(screen.getByLabelText("Other contact number"), { target: { value: "call me" } });
    expect(screen.getByText(/digits, spaces/)).toBeInTheDocument();
    expect(screen.getByText("Save contact")).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Other contact number"), { target: { value: "+94 71 999 0000" } });
    fireEvent.click(screen.getByText("Save contact"));
    expect(onSave).toHaveBeenCalledWith("+94 71 999 0000");
  });

  it("handles missing numbers", () => {
    render(<DeliveryContactPanel order={{ employee_mobile_phone: null, employee_home_phone: null,
      delivery_contact_phone: null }} canEdit onSave={() => {}} />);
    expect(screen.getAllByText("Not in BambooHR")).toHaveLength(2);
    expect(screen.getByTestId("delivery-contact-current")).toHaveTextContent("None");
    expect(screen.queryByLabelText("Mobile")).toBeNull();
  });
});
