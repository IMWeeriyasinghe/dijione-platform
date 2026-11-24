import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

vi.mock("@dijione/design-system", () => ({
  Button: ({ children, onClick, disabled }: { children: ReactNode; onClick?: () => void; disabled?: boolean }) => (
    <button onClick={onClick} disabled={disabled}>{children}</button>
  ),
  FormField: ({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) => (
    <label>{label}{children}<span>{hint}</span></label>
  ),
}));
const { updateConfig } = vi.hoisted(() => ({ updateConfig: vi.fn() }));
vi.mock("@/lib/api", () => ({ updateConfig }));

import { AlertRecipientsSection, parseRecipients, recipientsError } from "../admin/settings/alert-recipients";

function wrap(ui: ReactNode) {
  return render(<QueryClientProvider client={new QueryClient()}>{ui}</QueryClientProvider>);
}

describe("alert recipients", () => {
  it("parses and validates", () => {
    expect(parseRecipients("A@x.com, b@x.com;\na@x.com")).toEqual(["a@x.com", "b@x.com"]);
    expect(recipientsError("a@x.com")).toBeNull();
    expect(recipientsError("nope")).toMatch(/Not a valid/);
  });

  it("saves only the recipients, normalised", async () => {
    updateConfig.mockResolvedValue({});
    wrap(<AlertRecipientsSection saved={null} />);
    fireEvent.change(screen.getByLabelText(/Alert recipients/), { target: { value: "P@dijitalteam.com, q@dijitalteam.com" } });
    fireEvent.click(screen.getByText("Save recipients"));
    await waitFor(() =>
      expect(updateConfig).toHaveBeenCalledWith({ ops_alert_recipients: "p@dijitalteam.com\nq@dijitalteam.com" }),
    );
  });

  it("blocks saving invalid addresses", () => {
    wrap(<AlertRecipientsSection saved={null} />);
    fireEvent.change(screen.getByLabelText(/Alert recipients/), { target: { value: "bad address" } });
    expect(screen.getByText("Save recipients")).toBeDisabled();
  });
});
