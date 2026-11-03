"use client";

import { useSyncExternalStore } from "react";

/** True when the viewport is at least `minWidth` px. Server render and
 *  environments without matchMedia (tests) report the desktop layout. */
export function useMinWidth(minWidth: number): boolean {
  const query = `(min-width: ${minWidth}px)`;
  return useSyncExternalStore(
    (cb) => {
      if (typeof window === "undefined" || !window.matchMedia) return () => {};
      const mq = window.matchMedia(query);
      mq.addEventListener("change", cb);
      return () => mq.removeEventListener("change", cb);
    },
    () => (typeof window === "undefined" || !window.matchMedia ? true : window.matchMedia(query).matches),
    () => true,
  );
}
