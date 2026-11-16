"use client";

import { exitViewAs } from "./view-as";
import type { ViewAsSessionData } from "./http";

/**
 * Shown on every page of every application for as long as a View-as session is in use, so nobody
 * can mistake it for a normal session. Inline styles on purpose: this package is shared by all apps
 * and must not depend on any one app's stylesheet.
 */
export function ViewAsBanner({ session, administrator }: { session: ViewAsSessionData; administrator?: string }) {
  return (
    <div
      role="status"
      aria-live="polite"
      data-testid="view-as-banner"
      style={{
        position: "sticky",
        top: 0,
        zIndex: 2147483000,
        display: "flex",
        flexWrap: "wrap",
        alignItems: "center",
        justifyContent: "space-between",
        gap: "8px 16px",
        padding: "8px 16px",
        background: "#8f2417",
        color: "#ffffff",
        fontSize: 14,
        lineHeight: 1.4,
        boxShadow: "0 1px 4px rgba(0,0,0,0.25)",
      }}
    >
      <span>
        <strong>Read-only View as {session.targetName}</strong> ({session.targetEmail}).
        {administrator ? ` Signed in as ${administrator}.` : ""} You see exactly what they see. Nothing you do here can
        change data, and this session is recorded.
      </span>
      <button
        type="button"
        onClick={() => void exitViewAs()}
        style={{
          background: "#ffefd5",
          color: "#8f2417",
          border: "none",
          borderRadius: 6,
          padding: "6px 14px",
          fontWeight: 600,
          cursor: "pointer",
        }}
      >
        Exit View as
      </button>
    </div>
  );
}
