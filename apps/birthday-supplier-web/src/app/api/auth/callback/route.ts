import { cookies } from "next/headers";
import { NextResponse } from "next/server";

/**
 * Microsoft Entra ID redirect target for the Birthday Supplier Portal
 * (Authorization Code + PKCE).
 *
 * This filesystem route is matched before the
 * `/api/birthday/supplier/auth/:path*` rewrite, so `/api/auth/callback` is
 * handled here.
 *
 * Reads `?code&state`, reads the httpOnly `dijibirthday_supplier_flow`
 * cookie set by `/login`, hands all three to birthday-api's
 * `/api/birthday/supplier/auth/token`, then returns a tiny bootstrap page
 * that stores the supplier session token in sessionStorage (the same key
 * `lib/supplier-auth.tsx` reads) and navigates to "/". A valid Microsoft /
 * guest identity with no ACTIVE SupplierUser comes back as a generic 403
 * shown on this page — no portal access.
 */
const BIRTHDAY_API_URL = process.env.BIRTHDAY_API_URL ?? "http://localhost:8003";
const FLOW_COOKIE = "dijibirthday_supplier_flow";
const TOKEN_KEY = "dijibirthday-supplier-token";
const TOKEN_EVENT = "dijibirthday-supplier-token-change";

function page(bodyScript: string): NextResponse {
  return new NextResponse(
    `<!doctype html><meta charset="utf-8"><title>Signing in…</title>` +
      `<body style="font-family:system-ui;padding:2rem;color:#24140f"></body>` +
      `<script>${bodyScript}</script>`,
    { headers: { "content-type": "text/html; charset=utf-8" } },
  );
}

export async function GET(request: Request) {
  const url = new URL(request.url);
  const code = url.searchParams.get("code");
  const state = url.searchParams.get("state");
  const err = url.searchParams.get("error_description") || url.searchParams.get("error");

  if (err) return page(`document.body.textContent=${JSON.stringify("Sign-in failed: " + err)};`);
  if (!code || !state) return page(`location.replace("/");`);

  const jar = await cookies();
  const flowToken = jar.get(FLOW_COOKIE)?.value;
  if (!flowToken) {
    return page(`document.body.textContent="Sign-in session expired. Please try again.";`);
  }

  let resp: Response;
  try {
    resp = await fetch(`${BIRTHDAY_API_URL}/api/birthday/supplier/auth/token`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ code, state, flow_token: flowToken }),
      cache: "no-store",
    });
  } finally {
    jar.delete(FLOW_COOKIE);
  }

  if (!resp.ok) {
    let detail = "Sign-in failed.";
    try {
      detail = (await resp.json()).detail ?? detail;
    } catch {
      /* keep default */
    }
    // 403 = authenticated but not an authorised supplier. Generic message.
    return page(
      `document.body.textContent=${JSON.stringify(detail)};` +
        `var a=document.createElement("a");a.href="/";a.textContent="Back";` +
        `a.style="display:inline-block;margin-top:1rem;color:#c9431d";document.body.appendChild(a);`,
    );
  }

  const { access_token } = (await resp.json()) as { access_token: string };
  return page(
    `try{sessionStorage.setItem(${JSON.stringify(TOKEN_KEY)},${JSON.stringify(access_token)});` +
      `window.dispatchEvent(new Event(${JSON.stringify(TOKEN_EVENT)}));}catch(e){}` +
      `location.replace("/");`,
  );
}
