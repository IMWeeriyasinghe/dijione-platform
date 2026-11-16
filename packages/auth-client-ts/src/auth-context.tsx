"use client";

import {
  BIRTHDAY_STAFF_ROLES,
  MODULE_BIRTHDAY,
  MODULE_TALENT_FLOW,
  STAFF_ROLES,
  type CurrentUser,
} from "@dijione/contracts";
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { devLogin, getMe, refreshSession } from "./auth-api";
import { ApiError, getToken, setToken } from "./http";

type AuthContextValue = {
  user: CurrentUser | null;
  loading: boolean;
  login: (personaKey: string) => Promise<void>;
  logout: () => void;
};

const AuthContext = createContext<AuthContextValue | null>(null);

/** How long a tab may sit before returning to it picks up access changes. */
const REFRESH_AFTER_MS = 5 * 60 * 1000;

/**
 * Loads the signed-in user with their current access. The session token is
 * re-issued first, so a grant or revocation made in the Admin Center applies
 * on the next page load instead of at the next sign-in. A 401 means the
 * session is over. Any other refresh failure (an older platform-api without
 * the endpoint, a brief outage) keeps the existing token and reads the user.
 */
export async function loadSessionUser(): Promise<CurrentUser> {
  const tokenAtStart = getToken();
  try {
    const { access_token, user } = await refreshSession();
    // Do not resurrect a session that was signed out or replaced meanwhile.
    if (getToken() === tokenAtStart) setToken(access_token);
    return user;
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) throw error;
    return getMe();
  }
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    let lastLoadedAt = 0;

    async function restoreSession(initial: boolean) {
      const token = getToken();
      if (!token) {
        if (!cancelled) {
          if (!initial) setUser(null);
          setLoading(false);
        }
        return;
      }
      lastLoadedAt = Date.now();
      try {
        const restoredUser = await loadSessionUser();
        if (!cancelled) setUser(restoredUser);
      } catch (error) {
        // Only an authoritative "not signed in" ends the session; a failed
        // background check must not sign a working user out.
        if (initial || (error instanceof ApiError && error.status === 401)) {
          setToken(null);
          if (!cancelled) setUser(null);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    function onVisible() {
      if (document.visibilityState === "visible" && Date.now() - lastLoadedAt > REFRESH_AFTER_MS) {
        void restoreSession(false);
      }
    }

    void restoreSession(true);
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      cancelled = true;
      document.removeEventListener("visibilitychange", onVisible);
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

/** DijiBirthday module-role scope for the current user, or null if they
 * hold no role in the module. Note: this drives client-side UI only (e.g.
 * hiding Hold/Release/Cancel buttons) — every mutating birthday-api route
 * re-checks the caller's permission set server-side via
 * `require_birthday_permission`, so this hook is never the sole
 * enforcement point. */
export function useBirthdayScope() {
  const { user } = useAuth();
  return useMemo(() => {
    if (!user) return null;
    const role = user.module_roles.find((r) => r.module_key === MODULE_BIRTHDAY);
    if (!role) return null;
    return {
      role: role.role,
      isAdmin: BIRTHDAY_STAFF_ROLES.has(role.role),
    };
  }, [user]);
}
