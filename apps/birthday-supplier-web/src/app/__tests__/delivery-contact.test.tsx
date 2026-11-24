import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { DeliveryContact } from "../delivery-contact";

describe("DeliveryContact", () => {
  it("shows the chosen number and the alternative, as tel: links", () => {
    render(<DeliveryContact order={{ address_verified: true, delivery_contact_phone: "+94 11 333 4444",
      alternative_contact_phone: "+94 77 111 2222" }} />);
    expect(screen.getByText("Contact number")).toBeInTheDocument();
    expect(screen.getByText("+94 11 333 4444").closest("a")).toHaveAttribute("href", "tel:+94113334444");
    expect(screen.getByText("Alternative number")).toBeInTheDocument();
    expect(screen.getByText("+94 77 111 2222")).toBeInTheDocument();
  });

  it("shows one number cleanly", () => {
    render(<DeliveryContact order={{ address_verified: true, delivery_contact_phone: "+94 77 555 6666",
      alternative_contact_phone: null }} />);
    expect(screen.getByText("+94 77 555 6666")).toBeInTheDocument();
    expect(screen.queryByText("Alternative number")).toBeNull();
  });

  it("shows a neutral state with no number, and nothing before verification", () => {
    const { rerender } = render(<DeliveryContact order={{ address_verified: true, delivery_contact_phone: null }} />);
    expect(screen.getByText("Contact number not available.")).toBeInTheDocument();
    rerender(<DeliveryContact order={{ address_verified: false, delivery_contact_phone: "+94 77 1" }} />);
    expect(screen.queryByText("+94 77 1")).toBeNull();
    expect(screen.getByText(/verified by Dijital Team/)).toBeInTheDocument();
  });
});
