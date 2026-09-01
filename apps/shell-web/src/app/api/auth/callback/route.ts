import { cookies } from "next/headers";
import { NextResponse } from "next/server";

/**
 * Microsoft Entra ID redirect target (Authorization Code + PKCE).
 *
 * This filesystem route is matched before the `/api/auth/:path*` rewrite in
 * next.config.ts, so `/api/auth/callback` is handled here while every other
 * `/api/auth/*` path is still proxied to platform-api.
 *
 * Reads `?code&state`, reads the httpOnly `dijione_entra_flow` cookie set by
 * `/login`, hands all three to platform-api's `/api/auth/entra/token`, then
 * returns a tiny bootstrap page that stores the DijiOne session token in
 * localStorage (same key the app already uses) and navigates to "/".
 */
const PLATFORM_API_URL = process.env.PLATFORM_API_URL ?? "http://localhost:8000";
const TOKEN_STORAGE_KEY = "dijione.devToken";

function page(script: string): NextResponse {
  return new NextResponse(
    `<!doctype html><meta charset="utf-8"><title>Signing in…</title><script>${script}</script>`,
    { headers: { "content-type": "text/html; charset=utf-8" } },
  );
}

export async function GET(request: Request) {
  const url = new URL(request.url);
  const code = url.searchParams.get("code");
  const state = url.searchParams.get("state");
  const err = url.searchParams.get("error_description") || url.searchParams.get("error");

  if (err) {
    return page(`document.body.textContent=${JSON.stringify("Sign-in failed: " + err)};`);
  }
  if (!code || !state) {
    return page(`location.replace("/");`);
  }

  const jar = await cookies();
  const flowToken = jar.get("dijione_entra_flow")?.value;
  if (!flowToken) {
    return page(`document.body.textContent="Sign-in session expired. Please try again.";`);
  }

  const resp = await fetch(`${PLATFORM_API_URL}/api/auth/entra/token`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ code, state, flow_token: flowToken }),
    cache: "no-store",
  });

  jar.delete("dijione_entra_flow");

  if (!resp.ok) {
    let detail = "Sign-in failed.";
    try {
      detail = (await resp.json()).detail ?? detail;
    } catch {
      /* keep default */
    }
    return page(`document.body.textContent=${JSON.stringify(detail)};`);
  }

  const { access_token } = (await resp.json()) as { access_token: string };
  return page(
    `try{localStorage.setItem(${JSON.stringify(TOKEN_STORAGE_KEY)},${JSON.stringify(access_token)});}catch(e){}location.replace("/");`,
  );
}
