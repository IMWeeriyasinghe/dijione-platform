import { NextResponse } from "next/server";

/**
 * Read-only impersonation landing (Phase 1.5 §C). An internal DijiBirthday
 * admin POSTs a short-lived, read-only supplier session token here (from
 * an auto-submitting form in birthday-web) and this returns a tiny
 * bootstrap page that stores it in sessionStorage — the same key
 * `lib/supplier-auth.tsx` reads — and navigates to "/". The token carries
 * only `birthday.portal.access`, so every action route 403s server-side;
 * `app-shell.tsx` also shows a banner and hides the action buttons.
 *
 * POST (form-encoded) so the bearer token never lands in the URL / history.
 */
const TOKEN_KEY = "dijibirthday-supplier-token";
const TOKEN_EVENT = "dijibirthday-supplier-token-change";

function page(script: string): NextResponse {
  return new NextResponse(
    `<!doctype html><meta charset="utf-8"><title>Opening preview…</title>` +
      `<body style="font-family:system-ui;padding:2rem;color:#24140f"></body>` +
      `<script>${script}</script>`,
    { headers: { "content-type": "text/html; charset=utf-8" } },
  );
}

export async function POST(request: Request) {
  const form = await request.formData();
  const token = form.get("token");
  if (typeof token !== "string" || !token) {
    return page(`document.body.textContent="No impersonation token supplied.";`);
  }
  return page(
    `try{sessionStorage.setItem(${JSON.stringify(TOKEN_KEY)}, ${JSON.stringify(token)});` +
      `window.dispatchEvent(new Event(${JSON.stringify(TOKEN_EVENT)}));}catch(e){}` +
      `location.replace("/");`,
  );
}
