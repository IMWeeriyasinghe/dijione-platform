import type { CurrentUser, DevPersona } from "@dijione/contracts";
import { request } from "./http";

// Platform Core's public auth surface — every app proxies these paths
// straight through to platform-api (see each app's next.config.ts).
export const listDevPersonas = () => request<DevPersona[]>("/api/auth/dev-personas");
export const devLogin = (persona_key: string) =>
  request<{ access_token: string; user: CurrentUser }>("/api/auth/dev-login", {
    method: "POST",
    body: JSON.stringify({ persona_key }),
  });
export const getMe = () => request<CurrentUser>("/api/auth/me");

// Tells the frontend which sign-in UI to show: the Dev Identity Mode
// persona switcher ("dev") or a "Sign in with Microsoft" button ("entra").
export const getAuthConfig = () =>
  request<{ auth_mode: "dev" | "entra" }>("/api/auth/config");

// Kick off Microsoft Entra ID sign-in. shell-web's /login route builds the
// authorize URL + PKCE flow cookie and 302s to Entra; the callback stores
// the DijiOne session token and returns here.
export function beginEntraLogin(): void {
  if (typeof window !== "undefined") window.location.assign("/login");
}

// End the DijiOne session and, in Entra mode, the Entra session too.
export const getLogoutUrl = () =>
  request<{ logout_url: string | null }>("/api/auth/logout");
