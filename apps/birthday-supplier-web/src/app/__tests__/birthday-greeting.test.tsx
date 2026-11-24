import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { BirthdayGreeting } from "../birthday-greeting";

describe("BirthdayGreeting", () => {
  it("shows the greeting under its label and preserves line breaks", () => {
    render(<BirthdayGreeting order={{ birthday_greeting: "Happy Birthday Ann!\n\nAll the best!!\n- Peter Ward" }} />);
    expect(screen.getByText("Birthday Greeting")).toBeInTheDocument();
    const body = screen.getByTestId("birthday-greeting").querySelector("p")!;
    expect(body.textContent).toBe("Happy Birthday Ann!\n\nAll the best!!\n- Peter Ward");
    expect(body.className).toContain("whitespace-pre-wrap");
  });

  it("renders markup as text, not HTML", () => {
    render(<BirthdayGreeting order={{ birthday_greeting: "<b>hi</b>" }} />);
    expect(screen.getByText("<b>hi</b>")).toBeInTheDocument();
  });

  it.each([null, undefined, "", "   \n "])("renders nothing for %j", (value) => {
    const { container } = render(<BirthdayGreeting order={{ birthday_greeting: value }} />);
    expect(container).toBeEmptyDOMElement();
  });
});
