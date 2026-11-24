import { describe, expect, it } from "vitest";
import { emailPlainText, isHtmlBody, sanitizeEmailHtml, EMAIL_PREVIEW_CSP } from "../email-html";

const ORDER_EMAIL = `<!doctype html><html><head><style>.x{color:#333}</style></head>
<body style="margin:0;font-family:Arial"><table width="600"><tr><td>
<h1>New Birthday Cake Order</h1><p>Order <b>BDAY-EMP252-2026-00621</b></p>
<a href="https://supplierportal-dev.dijitalteam.com/orders/7">Open in Supplier Portal</a>
</td></tr></table></body></html>`;

describe("sanitizeEmailHtml", () => {
  it("keeps the email formatting and adds a restrictive CSP", () => {
    const doc = sanitizeEmailHtml(ORDER_EMAIL)!;
    expect(doc).toContain("<table");
    expect(doc).toContain("<h1>New Birthday Cake Order</h1>");
    expect(doc).toContain('style="margin:0;font-family:Arial"');
    expect(doc).toContain(EMAIL_PREVIEW_CSP);
    expect(doc).toContain('href="https://supplierportal-dev.dijitalteam.com/orders/7"');
  });

  it("removes scripts, active elements and inline event handlers", () => {
    const doc = sanitizeEmailHtml(
      `<p onclick="alert(1)" onmouseover="x()">Hi</p><script>alert(2)</script><iframe src="https://evil"></iframe>` +
        `<form action="https://evil"><input></form><img src="x" onerror="alert(3)"><svg onload="alert(4)"></svg>`,
    )!;
    expect(doc).not.toMatch(/<script|<iframe|<form|<input|<svg|onclick|onmouseover|onerror|onload|alert\(/i);
    expect(doc).toContain("<p>Hi</p>");
  });

  it("strips javascript:, vbscript: and data: URLs but keeps safe links and inline images", () => {
    const doc = sanitizeEmailHtml(
      `<a href="javascript:alert(1)">a</a><a href=" JaVaScRiPt:x">b</a><a href="vbscript:x">c</a>` +
        `<a href="data:text/html,<script>x</script>">d</a><a href="mailto:p@x.com">e</a>` +
        `<img src="data:image/png;base64,iVBORw0KGgo="><div style="background:url(javascript:x)">f</div>`,
    )!;
    expect(doc).not.toMatch(/javascript:|vbscript:|data:text/i);
    expect(doc).toContain('href="mailto:p@x.com"');
    expect(doc).toContain('src="data:image/png;base64,iVBORw0KGgo="');
  });

  it("fails safely on malformed HTML", () => {
    const doc = sanitizeEmailHtml("<table><tr><td>Unclosed <b>bold<p>para");
    expect(doc).not.toBeNull();
    expect(doc).toContain("Unclosed");
  });
});

describe("emailPlainText / isHtmlBody", () => {
  it("never returns markup", () => {
    const text = emailPlainText(ORDER_EMAIL);
    expect(text).toContain("New Birthday Cake Order");
    expect(text).toContain("BDAY-EMP252-2026-00621");
    expect(text).not.toMatch(/<[a-z!/]/i);
  });

  it("leaves plain text unchanged", () => {
    expect(emailPlainText("Hello,\nyour order is ready.")).toBe("Hello,\nyour order is ready.");
  });

  it("uses the API flag and falls back to detection for older responses", () => {
    expect(isHtmlBody({ body: "<p>x</p>", body_format: "text" })).toBe(false);
    expect(isHtmlBody({ body: "plain", body_format: "html" })).toBe(true);
    expect(isHtmlBody({ body: "<!doctype html><html></html>" })).toBe(true);
    expect(isHtmlBody({ body: "a < b and c > d" })).toBe(false);
    expect(isHtmlBody({ body: null })).toBe(false);
  });
});
