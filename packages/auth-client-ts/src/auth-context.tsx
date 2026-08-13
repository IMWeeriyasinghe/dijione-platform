"use client";

import { MODULE_TALENT_FLOW, STAFF_ROLES, type CurrentUser } from "@dijione/contracts";
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { devLogin, getMe } from "./auth-api";
import { getToken, setToken } from "./http";

type AuthContextValue = {
  user: CurrentUser | null;
  loading: boolean;
  login: (personaKey: string) => Promise<void>;
  logout: () => void;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    async function restoreSession() {
      const token = getToken();
      if (!token) {
        if (!cancelled) setLoading(false);
        return;
      }
      try {
        const restoredUser = await getMe();
        if (!cancelled) setUser(restoredUser);
      } catch {
        setToken(null);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    restoreSession();
    return () => {
      cancelled = true;
    };
  }, []);

  const login = useCallback(async (personaKey: string) => {
    const { access_token, user } = await devLogin(personaKey);
    setToken(access_token);
    setUser(user);
  }, []);

  const logout = useCallback(() => {
    setToken(null);
    setUser(null);
  }, []);

  const value = useMemo(() => ({ user, loading, login, logout }), [user, loading, login, logout]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}

/** Whether the current user can access the DijiOne Admin Center — derived
 * from the backend-resolved permission set, never from a hardcoded role
 * name (the frontend never re-implements authorization decisions). */
export function usePlatformAdmin(): boolean {
  const { user } = useAuth();
  return useMemo(() => Boolean(user?.platform_permissions.includes("platform.admin.access")), [user]);
}

export function usePlatformPermission(permissionKey: string): boolean {
  const { user } = useAuth();
  return useMemo(
    () => Boolean(user?.platform_permissions.includes(permissionKey)),
    [user, permissionKey]
  );
}

/** DijiTalentFlow module-role scope for the current user, or null if they
 * hold no role in the module. */
export function useTalentScope() {
  const { user } = useAuth();
  return useMemo(() => {
    if (!user) return null;
    const role = user.module_roles.find((r) => r.module_key === MODULE_TALENT_FLOW);
    if (!role) return null;
    return {
      role: role.role,
      clientId: role.client_id,
      isStaff: STAFF_ROLES.has(role.role),
      isClient: role.role === "TALENT_CLIENT",
      isCustomerSuccessOrManager: role.role === "CUSTOMER_SUCCESS" || role.role === "TA_MANAGER",
    };
  }, [user]);
}
