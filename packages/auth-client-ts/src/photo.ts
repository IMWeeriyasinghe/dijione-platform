"use client";

import { useEffect, useState } from "react";
import { authorizedFetch } from "./http";

/**
 * Loads an image from a DijiOne endpoint that needs the session token (an <img> tag cannot send it)
 * and returns an object URL for it, or null while loading, when there is no image (404) or on any
 * error, so the caller shows initials instead. The URL is revoked when the component unmounts or
 * the path changes. Only DijiOne's own API is called; no Microsoft Graph token reaches the browser.
 */
export function useAuthorizedImage(path: string | null | undefined): string | null {
  const [url, setUrl] = useState<string | null>(null);

  useEffect(() => {
    setUrl(null);
    if (!path) return;
    let cancelled = false;
    let objectUrl: string | null = null;
    authorizedFetch(path)
      .then(async (res) => {
        if (!res.ok || cancelled) return;
        const type = res.headers.get("content-type") ?? "";
        if (!type.startsWith("image/")) return;
        const blob = await res.blob();
        if (cancelled) return;
        objectUrl = URL.createObjectURL(blob);
        setUrl(objectUrl);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [path]);

  return url;
}
