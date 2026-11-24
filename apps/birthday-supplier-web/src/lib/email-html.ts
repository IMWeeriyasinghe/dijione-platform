// Safe rendering of stored email bodies in the order activity timeline.
//
// Email HTML is untrusted content. It is shown only inside an iframe with an
// empty `sandbox` attribute (no scripts, no same-origin access, no forms, no
// popups, no top navigation) and a restrictive Content-Security-Policy, and
// it is sanitised here first as defence in depth: active elements, event
// handlers and javascript:/vbscript:/data: URLs are removed. It can never
// run code or change the portal page around it.

const BLOCKED_TAGS = [
  "script", "iframe", "frame", "frameset", "object", "embed", "applet", "form", "input",
  "button", "textarea", "select", "link", "meta", "base", "svg", "math", "noscript", "template",
];
const URL_ATTRS = ["href", "src", "action", "formaction", "background", "poster", "xlink:href", "srcset"];
const SAFE_URL = /^(https?:|mailto:|tel:|#|\/(?!\/))/i;
const SAFE_IMAGE_DATA = /^data:image\/(png|gif|jpe?g|webp);base64,/i;

const HTML_MARKER = /<\s*(!doctype|html|head|body|table|div|p|br|span|a|td|tr|style)\b/i;

export const EMAIL_PREVIEW_CSP =
  "default-src 'none'; img-src https: data:; style-src 'unsafe-inline'; font-src https: data:";

const PREVIEW_BASE_STYLE =
  "html,body{margin:0;padding:0;background:#fff;}" +
  "body{padding:8px;overflow-wrap:anywhere;word-break:break-word;}" +
  "img{max-width:100%!important;height:auto!important;}" +
  "table{max-width:100%!important;}";

export type TimelineBody = { body: string | null; body_format?: "html" | "text" };

export function isHtmlBody(entry: TimelineBody): boolean {
  if (!entry.body) return false;
  if (entry.body_format) return entry.body_format === "html";
  return HTML_MARKER.test(entry.body); // older API responses without the flag
}

function parse(html: string): Document | null {
  try {
    if (typeof DOMParser === "undefined") return null;
    return new DOMParser().parseFromString(html, "text/html");
  } catch {
    return null;
  }
}

/** Sanitised, self-contained HTML document for the sandboxed preview, or
 * null when the body cannot be parsed (callers then show plain text). */
export function sanitizeEmailHtml(html: string): string | null {
  const doc = parse(html);
  if (!doc || !doc.body) return null;

  doc.querySelectorAll(BLOCKED_TAGS.join(",")).forEach((el) => el.remove());
  doc.querySelectorAll("*").forEach((el) => {
    for (const attr of Array.from(el.attributes)) {
      const name = attr.name.toLowerCase();
      const value = attr.value.trim();
      if (name.startsWith("on")) {
        el.removeAttribute(attr.name);
      } else if (URL_ATTRS.includes(name)) {
        const imageData = name === "src" && el.tagName === "IMG" && SAFE_IMAGE_DATA.test(value);
        if (!imageData && !SAFE_URL.test(value)) el.removeAttribute(attr.name);
      } else if (name === "style" && /expression\s*\(|javascript:|url\s*\(\s*['"]?\s*javascript:/i.test(value)) {
        el.removeAttribute(attr.name);
      }
    }
  });
  doc.querySelectorAll("style").forEach((el) => {
    if (/@import|javascript:|expression\s*\(/i.test(el.textContent ?? "")) el.remove();
  });

  const head =
    `<meta http-equiv="Content-Security-Policy" content="${EMAIL_PREVIEW_CSP}">` +
    `<style>${PREVIEW_BASE_STYLE}</style>` +
    Array.from(doc.head?.querySelectorAll("style") ?? []).map((s) => s.outerHTML).join("");
  // Keep the (sanitised) <body> element itself: emails put their layout styles on it.
  return `<!doctype html><html><head>${head}</head>${doc.body.outerHTML}</html>`;
}

/** Readable plain text from an HTML or text body; never returns markup. */
export function emailPlainText(body: string): string {
  if (!HTML_MARKER.test(body)) return body.trim();
  const doc = parse(body);
  if (!doc) return body.replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim();
  doc.querySelectorAll("script,style,head,title").forEach((el) => el.remove());
  doc.querySelectorAll("br").forEach((el) => el.replaceWith("\n"));
  doc.querySelectorAll("p,div,tr,li,h1,h2,h3,h4,table").forEach((el) => el.append("\n"));
  return (doc.body?.textContent ?? "")
    .split("\n")
    .map((line) => line.replace(/[ \t ]+/g, " ").trim())
    .filter((line, i, all) => line !== "" || (i > 0 && all[i - 1] !== ""))
    .join("\n")
    .trim();
}
