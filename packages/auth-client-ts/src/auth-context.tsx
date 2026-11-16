"use client";

import {
  BIRTHDAY_STAFF_ROLES,
  MODULE_BIRTHDAY,
  MODULE_TALENT_FLOW,
  STAFF_ROLES,
  type CurrentUser,
} from "@dijione/contracts";
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { devLogin, getMe, refreshSession } from "./auth-api";
import {
  ApiError,
  SESSION_ENDED_EVENT,
  VIEW_AS_ENDED_EVENT,
  getToken,
  endViewAsLocally,
  getViewAsSession,
  setToken,
  type ViewAsSessionData,
} from "./http";
import { exitViewAs } from "./view-as";
import { ViewAsBanner } from "./view-as-banner";
import { MIN_REFRESH_GAP_MS, isExpired, msUntilRefresh, retryDelayMs, tokenExpiryMs } from "./session-timing";

type AuthContextValue = {
  user: CurrentUser | null;
  loading: boolean;
  login: (personaKey: string) => Promise<void>;
  logout: () => void;
};

const AuthContext = createContext<AuthContextValue | null>(null);

/** How long a tab may sit before returning to it picks up access changes. REFRESH_LEAD_MS
 *  (imported) separately keeps the token itself from running out. */
const REFRESH_AFTER_MS = 5 * 60 * 1000;

/**
 * Loads the signed-in user with their current access. The session token is
 * re-issued first, so a grant or revocation made in the Admin Center applies
 * on the next page load instead of at the next sign-in. A 401 means the
 * session is over. Any other refresh failure (an older platform-api without
 * the endpoint, a brief outage) keeps the existing token and reads the user.
 */
export async function loadSessionUser(): Promise<CurrentUser> {
  // A View-as session is read-only and cannot be refreshed: just read who is being viewed.
  if (getViewAsSession()) return getMe();
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
  const scheduleRefresh = useRef<(() => void) | null>(null);
  // Read after mount (sessionStorage does not exist on the server) so the first client render matches it.
  const [viewAs, setViewAs] = useState<ViewAsSessionData | null>(null);

  useEffect(() => {
    let cancelled = false;
    let lastLoadedAt = 0;
    // Fixed for this page load. Read from storage at the time of a failure it could already be gone
    // (a failed request ends the View-as session), and the staff session would then be cleared by mistake.
    const viewAsAtMount = getViewAsSession();
    let timer: ReturnType<typeof setTimeout> | undefined;
    let failures = 0;

    function endSession() {
      // In a View-as tab the staff session is not this tab's to end: leave only the View-as session.
      if (viewAsAtMount) return endViewAsLocally();
      setToken(null);
      if (!cancelled) setUser(null);
    }

    // "ok": a current token is stored. "failed": nothing authoritative was learned
    // (network, outage); the token is kept. "ended": the server said the session is over.
    async function restoreSession(initial: boolean): Promise<"ok" | "failed" | "ended"> {
      const token = getToken();
      if (!token) {
        if (!cancelled) {
          if (!initial) setUser(null);
          setLoading(false);
        }
        return "ended";
      }
      lastLoadedAt = Date.now();
      try {
        const restoredUser = await loadSessionUser();
        if (!cancelled) setUser(restoredUser);
        return "ok";
      } catch (error) {
        // Only an authoritative "not signed in" ends the session; a failed
        // background check must not sign a working user out.
        if (initial || (error instanceof ApiError && error.status === 401)) {
          endSession();
          return "ended";
        }
        return "failed";
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    // Refresh shortly before the token expires, so a working session never runs out.
    // After a failure (network, brief outage) retry with backoff while the token is
    // still valid; once it has expired the session is over and the person signs in again.
    function schedule(delayOverride?: number) {
      if (timer) clearTimeout(timer);
      const token = getToken();
      if (!token || cancelled) return;
      const delay = delayOverride ?? msUntilRefresh(token);
      if (delay === null) return;
      timer = setTimeout(() => void runScheduledRefresh(), Math.max(delay, MIN_REFRESH_GAP_MS));
    }

    async function runScheduledRefresh() {
      const token = getToken();
      if (!token) return;
      if (isExpired(token)) return endSession();
      const outcome = await restoreSession(false);
      if (outcome === "ok") {
        failures = 0;
        // Near the 12-hour session limit a refresh no longer extends the token. Stop
        // scheduling then; the session simply runs to its end.
        const next = getToken();
        const before = tokenExpiryMs(token);
        const after = next ? tokenExpiryMs(next) : null;
        if (before === null || after === null || after > before) schedule();
      } else if (outcome === "failed") {
        schedule(retryDelayMs(failures++));
      }
    }

    async function onVisible() {
      if (document.visibilityState !== "visible") return;
      const token = getToken();
      if (!token) return;
      if (isExpired(token)) return endSession(); // a long sleep: it cannot be refreshed
      const due = (msUntilRefresh(token) ?? Infinity) === 0 || Date.now() - lastLoadedAt > REFRESH_AFTER_MS;
      if (due) {
        const outcome = await restoreSession(false);
        if (outcome === "ok") failures = 0;
      }
      schedule(failures ? retryDelayMs(failures - 1) : undefined);
    }

    function onSessionEnded() {
      if (!cancelled) setUser(null);
    }

    scheduleRefresh.current = () => schedule();
    // A View-as session ended without the person asking (expired, ended elsewhere, access changed):
    // go back to where the administrator started.
    function onViewAsEnded() {
      const back = viewAsAtMount?.returnTo || "/";
      window.location.assign(back);
    }

    setViewAs(viewAsAtMount);
    void restoreSession(true).then((outcome) => {
      // A View-as token is never refreshed, so nothing is scheduled for it.
      if (outcome === "ok" && !viewAsAtMount) schedule();
    });
    window.addEventListener(SESSION_ENDED_EVENT, onSessionEnded);
    window.addEventListener(VIEW_AS_ENDED_EVENT, onViewAsEnded);
    if (!viewAsAtMount) document.addEventListener("visibilitychange", onVisible);

    // A View-as session has a fixed end. When it comes (or if it has already passed, for a page opened late)
    // end it here and go back, so the banner never outlives the session it describes.
    let viewAsTimer: ReturnType<typeof setTimeout> | undefined;
    if (viewAsAtMount) {
      const remaining = Date.parse(viewAsAtMount.expiresAt) - Date.now();
      if (Number.isNaN(remaining) || remaining <= 0) endViewAsLocally();
      else viewAsTimer = setTimeout(() => endViewAsLocally(), remaining);
    }
    return () => {
      cancelled = true;
      scheduleRefresh.current = null;
      if (viewAsTimer) clearTimeout(viewAsTimer);
      if (timer) clearTimeout(timer);
      document.removeEventListener("visibilitychange", onVisible);
      window.removeEventListener(SESSION_ENDED_EVENT, onSessionEnded);
      window.removeEventListener(VIEW_AS_ENDED_EVENT, onViewAsEnded);
    };
  }, []);

  const login = useCallback(async (personaKey: string) => {
    const { access_token, user } = await devLogin(personaKey);
    setToken(access_token);
    setUser(user);
    scheduleRefresh.current?.(); // a new sign-in starts its own refresh cycle
  }, []);

  const logout = useCallback(() => {
    // In a View-as tab "sign out" means leave the View-as session; the administrator stays signed in.
    if (getViewAsSession()) {
      void exitViewAs();
      return;
    }
    setToken(null);
    setUser(null);
  }, []);

  const value = useMemo(() => ({ user, loading, login, logout }), [user, loading, login, logout]);

  return (
    <AuthContext.Provider value={value}>
      {viewAs && <ViewAsBanner session={viewAs} administrator={user?.view_as?.actor_name} />}
      {children}
    </AuthContext.Provider>
  );
}

/** Like ``useAuth`` but returns null outside an ``AuthProvider`` instead of throwing, for optional UI. */
export function useOptionalAuth(): AuthContextValue | null {
  return useContext(AuthContext);
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
