import { cookies } from "next/headers";
import { NextResponse } from "next/server";

/**
 * Starts the Microsoft Entra ID sign-in (Authorization Code + PKCE).
 *
 * Asks platform-api to build the authorize URL + a short-lived signed flow
 * token (carrying state/nonce/PKCE-verifier), stashes the flow token in an
 * httpOnly cookie on shell-web's own origin, and 302s the browser to Entra.
 * The `/api/auth/callback` route completes the exchange.
 *
 * In Dev Identity Mode this route is unused — the persona switcher handles
 * sign-in — and platform-api's /login-url returns 501, so we fall back to "/".
 */
const PLATFORM_API_URL = process.env.PLATFORM_API_URL ?? "http://localhost:8000";

export async function GET() {
  const resp = await fetch(`${PLATFORM_API_URL}/api/auth/entra/login-url`, {
    cache: "no-store",
  });
  if (!resp.ok) {
    return NextResponse.redirect(new URL("/", process.env.PUBLIC_BASE_URL ?? "http://localhost:3000"));
  }
  const { authorize_url, flow_token } = (await resp.json()) as {
    authorize_url: string;
    flow_token: string;
  };

  const jar = await cookies();
  jar.set("dijione_entra_flow", flow_token, {
    httpOnly: true,
    secure: true,
    sameSite: "lax",
    path: "/",
    maxAge: 600,
  });
  return NextResponse.redirect(authorize_url);
}
