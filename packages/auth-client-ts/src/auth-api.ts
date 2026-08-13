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
