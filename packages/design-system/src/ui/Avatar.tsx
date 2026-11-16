"use client";

import { useEffect, useState } from "react";
import { initials } from "../utils";

/** A person's photo when one is available (``src``), otherwise their initials. A photo that fails to
 * load also falls back to initials. Existing callers that pass no ``src`` are unchanged. */
export function Avatar({
  name,
  color,
  size = 36,
  src,
}: {
  name: string;
  color?: string | null;
  size?: number;
  src?: string | null;
}) {
  const [failed, setFailed] = useState(false);
  useEffect(() => setFailed(false), [src]);

  if (src && !failed) {
    return (
      // eslint-disable-next-line @next/next/no-img-element -- an object URL for an authorised blob
      <img
        src={src}
        alt=""
        aria-hidden
        width={size}
        height={size}
        onError={() => setFailed(true)}
        className="shrink-0 rounded-full object-cover"
        style={{ width: size, height: size }}
        data-testid="avatar-photo"
      />
    );
  }
  return (
    <div
      className="flex shrink-0 items-center justify-center rounded-full font-semibold text-white"
      style={{
        width: size,
        height: size,
        fontSize: size * 0.38,
        background: color ?? "var(--dt-burnt-orange)",
      }}
      aria-hidden
      data-testid="avatar-initials"
    >
      {initials(name) || "?"}
    </div>
  );
}
