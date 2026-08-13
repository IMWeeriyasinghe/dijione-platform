import type { ModuleOut } from "@dijione/contracts";
import { request } from "@dijione/auth-client";

// Platform Core's module registry — proxied to platform-api via this app's
// next.config.ts rewrites.
export const listModules = () => request<ModuleOut[]>("/api/modules");
