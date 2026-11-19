#!/usr/bin/env node
// Validates the end-user documentation: relative links, image references,
// in-page anchors, required manual sections, unreferenced screenshots, and a
// sensitive-text scan. Usage: node docs/end-user/tools/check-docs.mjs
// Exits non-zero when an error is found.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const walk = (d) => fs.readdirSync(d, { withFileTypes: true }).flatMap((e) =>
  e.isDirectory() ? (e.name === "pdf" || e.name === "tools" ? [] : walk(path.join(d, e.name))) : [path.join(d, e.name)]);
const files = walk(root);
const mdFiles = files.filter((f) => f.endsWith(".md"));
const pngs = files.filter((f) => f.endsWith(".png"));

const slug = (h) => h.toLowerCase().trim().replace(/<[^>]+>/g, "")
  .replace(/[ -⁯⸀-⹿\\'!"#$%&()*+,./:;<=>?@[\]^`{|}~]/g, "").replace(/\s/g, "-");
const anchorsOf = (f) => {
  const seen = {};
  return new Set(fs.readFileSync(f, "utf8").split("\n").filter((l) => /^#{1,6} /.test(l)).map((l) => {
    let s = slug(l.replace(/^#+ /, ""));
    if (seen[s] !== undefined) s = `${s}-${++seen[s]}`; else seen[s] = 0;
    return s;
  }));
};

const errors = [], warnings = [];
const referenced = new Set();
let links = 0, images = 0;
for (const f of mdFiles) {
  const text = fs.readFileSync(f, "utf8");
  for (const m of text.matchAll(/(!?)\[[^\]]*\]\(([^)\s]+)(?:\s+"[^"]*")?\)/g)) {
    const [, bang, target] = m;
    if (/^(https?:|mailto:)/.test(target)) continue;
    const [p, anchor] = target.split("#");
    const resolved = p ? path.resolve(path.dirname(f), decodeURI(p)) : f;
    if (bang) { images++; referenced.add(resolved); } else links++;
    if (p && !fs.existsSync(resolved)) {
      if (resolved.includes(`${path.sep}pdf${path.sep}`)) warnings.push(`${path.relative(root, f)}: PDF not built yet: ${target}`);
      else errors.push(`${path.relative(root, f)}: missing ${bang ? "image" : "link target"} ${target}`);
      continue;
    }
    if (anchor && resolved.endsWith(".md") && !anchorsOf(resolved).has(anchor))
      errors.push(`${path.relative(root, f)}: missing anchor #${anchor} in ${p || "same file"}`);
  }
}

const REQUIRED = ["A. Introduction", "B. Getting started", "C. Understanding the interface", "D. User roles and permissions",
  "E. Step-by-step workflows", "F. Role-specific operating guides", "G. Common scenarios", "H. Troubleshooting and FAQs",
  "I. Glossary", "J. Quick reference", "K. Document information"];
// The DijiAtWork V1 manual (version 2.0) follows the owner-requested A-N structure.
const REQUIRED_BY_MANUAL = {
  "04-diji-at-work": ["A. Introduction", "B. Accessing DijiAtWork", "C. Employee: Today", "D. Employee: Attendance history",
    "E. Employee: Attendance corrections", "F. Notifications", "G. Management: Overview",
    "H. Management: Employees and sessions", "I. Management: Corrections", "J. Management: Reports and exports",
    "K. Management: Settings and audit", "L. Common problems and troubleshooting", "M. Frequently asked questions",
    "N. Support and document control"],
};
for (const f of mdFiles.filter((x) => x.endsWith("user-manual.md"))) {
  const t = fs.readFileSync(f, "utf8");
  const required = REQUIRED_BY_MANUAL[path.basename(path.dirname(f))] || REQUIRED;
  for (const h of required) if (!t.includes(`## ${h}`)) errors.push(`${path.relative(root, f)}: missing section "${h}"`);
  if (/\b(TODO|TBD|lorem ipsum)\b/i.test(t)) errors.push(`${path.relative(root, f)}: placeholder text`);
}

for (const p of pngs) if (p.includes(`${path.sep}annotated${path.sep}`) && !fs.existsSync(path.join(path.dirname(p), "..", path.basename(p))))
  errors.push(`annotated screenshot without its original: ${path.relative(root, p)}`);
for (const p of pngs) if (!referenced.has(p) && !referenced.has(path.join(path.dirname(p), "annotated", path.basename(p)))) {
  const manifest = fs.readFileSync(path.join(root, "shared/screenshot-manifest.md"), "utf8");
  if (!manifest.includes(path.basename(p))) errors.push(`screenshot not in manifest: ${path.relative(root, p)}`);
  else warnings.push(`screenshot not used in a manual (manifest only): ${path.relative(root, p)}`);
}

const SENSITIVE = [/eyJ[A-Za-z0-9_-]{20,}/, /dev-only-(internal|insecure)-secret/, /\bcli-[a-z0-9-]{3,}/, /@dijitalteam\.com/,
  /access#[A-Za-z0-9_-]{10,}/, /password\s*[:=]/i, /\bDiji1\b|\bDG1\b/];
for (const f of mdFiles) {
  const t = fs.readFileSync(f, "utf8");
  for (const re of SENSITIVE) if (re.test(t)) errors.push(`${path.relative(root, f)}: sensitive/forbidden pattern ${re}`);
}

console.log(`Checked ${mdFiles.length} Markdown files, ${links} links, ${images} image references, ${pngs.length} screenshots.`);
for (const w of warnings) console.log(`WARN  ${w}`);
for (const e of errors) console.log(`ERROR ${e}`);
console.log(errors.length ? `FAILED: ${errors.length} error(s)` : "PASSED: no errors");
process.exit(errors.length ? 1 : 0);
