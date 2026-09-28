import { cookies } from "next/headers";
import { NextResponse } from "next/server";

/**
 * Starts Microsoft Entra ID B2B guest sign-in for the Birthday Supplier
 * Portal (Authorization Code + PKCE).
 *
 * Asks birthday-api to build the authorize URL + a short-lived signed flow
 * token (state / nonce / PKCE verifier), stashes the flow token in an
 * httpOnly cookie on this app's own origin, and 302s the browser to
 * Microsoft. `/api/auth/callback` completes the exchange.
 *
 * When SUPPLIER_AUTH_MODE=dev, birthday-api's /login-url returns 501 and
 * this route just sends the user back to "/" (the persona picker there).
 */
const BIRTHDAY_API_URL = process.env.BIRTHDAY_API_URL ?? "http://localhost:8003";
const FLOW_COOKIE = "dijibirthday_supplier_flow";

// Same-origin relative path only — mirrors birthday-api's own
// _sanitize_return_to (defense in depth, not the only check: the backend
// re-validates this again before it ever reaches the signed flow token).
const SAFE_RETURN_TO = /^\/[A-Za-z0-9/_-]*$/;

function sanitizeReturnTo(value: string | null): string | null {
  if (!value) return null;
  if (value.startsWith("//") || value.includes(":")) return null;
  return SAFE_RETURN_TO.test(value) ? value : null;
}

export async function GET(request: Request) {
  const home = new URL("/", process.env.SUPPLIER_PUBLIC_BASE_URL ?? "http://localhost:3000");
  const returnTo = sanitizeReturnTo(new URL(request.url).searchParams.get("return_to"));

  let resp: Response;
  try {
    const loginUrlEndpoint = new URL(`${BIRTHDAY_API_URL}/api/birthday/supplier/auth/login-url`);
    if (returnTo) loginUrlEndpoint.searchParams.set("return_to", returnTo);
    resp = await fetch(loginUrlEndpoint, { cache: "no-store" });
  } catch {
    return NextResponse.redirect(home);
  }
  if (!resp.ok) return NextResponse.redirect(home);

  const { authorize_url, flow_token } = (await resp.json()) as {
    authorize_url: string;
    flow_token: string;
  };

  const jar = await cookies();
  jar.set(FLOW_COOKIE, flow_token, {
    httpOnly: true,
    secure: true,
    sameSite: "lax",
    path: "/",
    maxAge: 600,
  });
  return NextResponse.redirect(authorize_url);
}
