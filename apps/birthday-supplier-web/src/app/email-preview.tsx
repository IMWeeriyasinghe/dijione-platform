"use client";

import { useMemo, useState } from "react";
import { emailPlainText, sanitizeEmailHtml } from "@/lib/email-html";

const COLLAPSED_HEIGHT = 320;
const EXPANDED_HEIGHT = 900;

/** Contained preview of a stored HTML email: sanitised, inside an iframe
 * with an empty sandbox (no scripts, no same-origin, no forms/popups), so it
 * keeps its formatting but can never affect the portal page. Falls back to
 * clean plain text if the HTML cannot be rendered. */
export function EmailPreview({ html, subject }: { html: string; subject?: string | null }) {
  const doc = useMemo(() => sanitizeEmailHtml(html), [html]);
  const [expanded, setExpanded] = useState(false);

  if (!doc) {
    return (
      <p className="mt-1 whitespace-pre-wrap text-sm text-dt-text-secondary" data-testid="email-plain-text">
        {emailPlainText(html)}
      </p>
    );
  }

  return (
    <div className="mt-2 w-full max-w-full overflow-hidden rounded-md border border-dt-border bg-white">
      <iframe
        title={subject ? `Email: ${subject}` : "Email preview"}
        sandbox=""
        referrerPolicy="no-referrer"
        srcDoc={doc}
        className="block w-full border-0"
        style={{ height: expanded ? EXPANDED_HEIGHT : COLLAPSED_HEIGHT }}
        data-testid="email-preview"
      />
      <div className="flex justify-end border-t border-dt-border px-2 py-1">
        <button
          type="button"
          className="text-xs font-medium text-dt-burnt-orange underline-offset-2 hover:underline"
          onClick={() => setExpanded((v) => !v)}
        >
          {expanded ? "Show less" : "Show full email"}
        </button>
      </div>
    </div>
  );
}
