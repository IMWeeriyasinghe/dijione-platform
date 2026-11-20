#!/usr/bin/env node
// Builds PDF copies of the end-user manuals from their Markdown source.
// Usage (from the repo root, after `npm ci`):  node docs/end-user/tools/build-pdf.mjs
// Uses only dependencies already in the workspace (marked, puppeteer).
// The Markdown files remain the source of truth; PDFs are generated output.
//
// Layout rules (applied in the browser before printing; source PNGs are never modified):
//  - every screenshot becomes a numbered figure with its alt text as the caption;
//  - all desktop screenshots print at one scale (1440 px = 150 mm), phone
//    captures at phone size, and no figure is taller than MAX_FIG_MM;
//  - two or more screenshots written on adjacent lines are laid out side by side;
//  - a figure is kept on the same page as the instruction directly above it;
//  - only the major sections start on a new page, to avoid half-empty pages;
//  - ```mermaid code blocks are rendered as diagrams with the Mermaid library
//    already in the workspace (node_modules/mermaid). A diagram that fails to
//    parse stops the build, so a broken diagram never reaches a PDF.
import { createRequire } from "node:module";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "..");
const require = createRequire(path.resolve(root, "../../package.json"));
const { marked } = require("marked");
const puppeteer = require("puppeteer");

const MANUALS = [
  ["00-dijione-platform", "DijiOne Platform"],
  ["01-dijitalentflow", "DijiTalentFlow"],
  ["02-diji-birthday", "DIJI Birthday"],
  ["03-diji-on-site", "Diji On-site"],
  ["04-diji-at-work", "DijiAtWork V1"],
];
// Sections that always start on a new page (the others follow on).
const NEW_PAGE_SECTIONS = ["f-role-specific-operating-guides"];
const pdfName = (dir) => `${dir}-user-manual.pdf`;
const MERMAID_JS = pathToFileURL(path.dirname(require.resolve("mermaid/package.json")) + "/dist/mermaid.min.js").href;

const CSS = `
@page { size: A4; margin: 20mm 18mm 20mm 18mm; }
* { box-sizing: border-box; }
html { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
body { font-family: "Helvetica Neue", Helvetica, Arial, sans-serif; color: #24140f; font-size: 10pt; line-height: 1.45; margin: 0; orphans: 3; widows: 3; }
p { margin: 0 0 6pt; }
ul, ol { margin: 0 0 6pt; padding-left: 16pt; }
li { margin: 0 0 3pt; }
li > p { margin: 0 0 3pt; }
strong { color: #24140f; font-weight: 600; }
hr { display: none; }
body > h1:first-of-type { display: none; }
h2 { color: #8f2417; font-size: 17pt; font-weight: 600; margin: 20pt 0 8pt; padding-bottom: 4pt; border-bottom: 2px solid #f26a1b; break-after: avoid; }
h2.newpage { break-before: page; margin-top: 0; }
h3 { color: #aa2f1d; font-size: 12pt; font-weight: 600; margin: 14pt 0 5pt; break-after: avoid; }
h2 + h3 { margin-top: 6pt; }
h3.wf { border-left: 3px solid #f26a1b; padding-left: 7pt; }
a { color: #c9431d; text-decoration: none; }
code { font-family: Menlo, Consolas, monospace; background: #fff3e6; padding: 0 2pt; border-radius: 2pt; font-size: 8.5pt; }
table { border-collapse: collapse; width: 100%; margin: 4pt 0 8pt; font-size: 8.8pt; line-height: 1.35; }
thead { display: table-header-group; }
th, td { border: 0.6pt solid #e3cfc4; padding: 3pt 5pt; text-align: left; vertical-align: top; }
th { background: #fbeee2; font-weight: 600; color: #5a2a1c; }
tr { break-inside: avoid; }
td:first-child { font-weight: 500; }
table.meta td:first-child { width: 28%; background: #fffaf4; color: #76584c; }
blockquote { border-left: 3px solid #f59e0b; background: #fff8ef; margin: 6pt 0 8pt; padding: 5pt 9pt; break-inside: avoid; }
blockquote p { margin: 0 0 3pt; }
blockquote p:last-child { margin: 0; }
figure.shot { margin: 6pt auto 10pt; break-inside: avoid; text-align: center; }
figure.shot img { display: block; margin: 0 auto; border: 0.6pt solid #e3cfc4; border-radius: 3pt; }
figure.shot figcaption { font-size: 8pt; color: #76584c; margin-top: 3pt; font-style: italic; }
.pair { display: flex; gap: 5mm; justify-content: center; align-items: flex-start; margin: 6pt 0 10pt; break-inside: avoid; }
.pair figure.shot { margin: 0; flex: 1 1 0; }
.pair figure.shot img { max-width: 100%; height: auto !important; }
.keep { break-inside: avoid; }
li .keep, li figure.shot { margin-left: 0; }
.cover { height: 247mm; display: flex; flex-direction: column; justify-content: center; break-after: page; border-left: 6px solid #f26a1b; padding-left: 14mm; }
.cover .brand { color: #c9431d; letter-spacing: .14em; text-transform: uppercase; font-size: 9.5pt; font-weight: 600; }
.cover h1 { font-size: 34pt; color: #8f2417; margin: 6pt 0 2pt; font-weight: 600; }
.cover .sub { font-size: 16pt; color: #aa2f1d; }
.cover .meta { color: #76584c; margin-top: 22pt; font-size: 9.5pt; line-height: 1.6; }
.intro { font-size: 10.5pt; break-before: page; }
table.control { border-top: 2pt solid #f26a1b; margin: 2pt 0 6pt; font-size: 8.8pt; break-inside: avoid; }
table.control td { padding: 3.5pt 6pt; }
table.control td:first-child { width: 31%; background: #fbeee2; color: #5a2a1c; font-weight: 600; }
table.control + p.subhead, #document-control + p.subhead { margin-top: 8pt; }
table.revisions { font-size: 8.5pt; }
table.revisions th:nth-child(1), table.revisions td:nth-child(1) { width: 11mm; }
table.revisions th:nth-child(2), table.revisions td:nth-child(2) { width: 24mm; }
table.revisions th:nth-child(4), table.revisions td:nth-child(4) { width: 34mm; }
table.revisions th:nth-child(5), table.revisions td:nth-child(5) { width: 28mm; }
.toc { margin: 4pt 0 10pt; }
.toc a { display: flex; align-items: baseline; color: #24140f; text-decoration: none; padding: 1.2pt 0; break-inside: avoid; }
.toc .dots { flex: 1; border-bottom: 0.7pt dotted #c9b2a6; margin: 0 5pt; position: relative; top: -2.5pt; }
.toc .pg { font-variant-numeric: tabular-nums; min-width: 12pt; text-align: right; }
.toc a.toc-main { font-weight: 600; font-size: 10pt; margin-top: 3.5pt; }
.toc a.toc-sub { font-size: 9pt; color: #4a332a; padding-left: 12pt; }
table.diagram-index th.num, table.diagram-index td.num { text-align: right; width: 13mm; font-variant-numeric: tabular-nums; }
figure.diagram { margin: 8pt auto 6pt; break-inside: avoid; text-align: center; }
figure.diagram svg { max-width: 100%; height: auto; }
figure.diagram figcaption { font-size: 8pt; color: #76584c; margin-top: 3pt; font-style: italic; }
figure.diagram + p { break-before: avoid; break-inside: avoid; }
p.subhead { font-weight: 600; color: #5a2a1c; margin: 9pt 0 4pt; break-after: avoid; }
p.leadin, li > p:has(+ ul), li > p:has(+ ol) { break-after: avoid; }
table.meta { break-after: avoid; break-inside: avoid; }
blockquote { break-before: avoid; }
`;

function render(dir, title) {
  const mdPath = path.join(root, dir, "user-manual.md");
  let md = fs.readFileSync(mdPath, "utf8");
  // cross-manual links -> sibling PDFs; other repo docs -> plain text reference
  md = md.replace(/\]\(\.\.\/(0\d-[a-z-]+)\/user-manual\.md(#[^)]*)?\)/g, (_, d) => `](${pdfName(d)})`);
  md = md.replace(/\[([^\]]+)\]\(\.\.\/(shared|validation)\/([^)#]+)(#[^)]*)?\)/g, (_, t) => `${t} (in the DijiOne documentation library)`);
  md = md.replace(/\[([^\]]+)\]\(\.\.\/README\.md\)/g, (_, t) => `${t} (in the DijiOne documentation library)`);
  marked.setOptions({ headerIds: true, headerPrefix: "", mangle: false, gfm: true });
  // Images are embedded as data URLs so the page can read their pixels (for trimming).
  const body = marked.parse(md).replace(/<img src="([^"]+)"/g, (m, src) => {
    const f = path.join(root, dir, decodeURI(src));
    return fs.existsSync(f) ? `<img data-src="${src}" src="data:image/png;base64,${fs.readFileSync(f).toString("base64")}"` : m;
  });
  // Cover metadata comes from the manual's own "K. Document information" table.
  // Cover and footer metadata come from the manual's own "Document control" tables.
  const field = (name) => (md.match(new RegExp(`\\| ${name} \\| (.*) \\|`)) || [, ""])[1].replace(/`/g, "").replace(/\*\*/g, "");
  const classification = (field("Classification").match(/^([A-Za-z -]+?)\./) || [, "Internal"])[1];
  const cover = `<section class="cover"><div class="brand">DijiOne | by Dijital Team</div><h1>${title}</h1>
    <div class="sub">User Manual</div>
    <div class="meta">Version ${field("Document version")} | ${field("Publication date")} | ${classification}<br>${field("Application version")}<br>Release ${field("Release reference")}</div></section>`;
  const base = pathToFileURL(path.join(root, dir) + "/").href;
  return {
    html: `<!doctype html><html><head><meta charset="utf-8"><base href="${base}"><title>${title} - User Manual</title><style>${CSS}</style><script src="${MERMAID_JS}"></script></head><body>${cover}${body}</body></html>`,
    version: field("Document version"), classification,
  };
}


// ---------------------------------------------------------------- in-page helpers
// Contents with page numbers (main sections, workflows and role guides) and a
// diagram index whose last column is the page number. Numbers start as "00"
// placeholders of the same width and are filled in after the first print pass.
function buildNavigation() {
  // Document control: labelled key/value tables; revision history: fixed column widths.
  const dc = document.getElementById("document-control");
  for (let el = dc && dc.nextElementSibling; el && el.tagName !== "H2"; el = el.nextElementSibling)
    if (el.tagName === "TABLE") el.classList.add("control");
  // Keep each group (sub-heading + table) on one page.
  for (const t of [...document.querySelectorAll("table.control")]) {
    const k = document.createElement("div"); k.className = "keep";
    const head = t.previousElementSibling && t.previousElementSibling.matches("p.subhead") ? t.previousElementSibling : null;
    (head || t).before(k); if (head) k.append(head); k.append(t);
  }
  const rh = document.getElementById("revision-history");
  for (let el = rh && rh.nextElementSibling; el && el.tagName !== "H2"; el = el.nextElementSibling)
    if (el.tagName === "TABLE") el.classList.add("revisions");
  const contentsH = document.getElementById("contents");
  if (contentsH) {
    const list = contentsH.nextElementSibling;
    const toc = document.createElement("div"); toc.className = "toc";
    let section = "";
    for (const h of document.querySelectorAll("h2, h3")) {
      if (h.closest(".cover") || h.id === "contents") continue;
      if (h.tagName === "H2") section = h.id;
      const isSub = h.tagName === "H3";
      if (isSub && !/^e-|^f-/.test(section)) continue;
      const a = document.createElement("a"); a.href = `#${h.id}`; a.className = isSub ? "toc-sub" : "toc-main";
      a.innerHTML = `<span class="t"></span><span class="dots"></span><span class="pg" data-target="${h.id}">00</span>`;
      a.querySelector(".t").textContent = h.textContent;
      toc.append(a);
    }
    if (list && list.tagName === "UL") list.replaceWith(toc); else contentsH.after(toc);
  }
  const di = document.getElementById("workflow-diagrams");
  if (di) {
    let t = di.nextElementSibling; while (t && t.tagName !== "TABLE") t = t.nextElementSibling;
    if (t) {
      const ths = [...t.querySelectorAll("thead th")];
      const where = ths.length - 1;
      ths[where].textContent = "Page"; ths[where].classList.add("num");
      t.classList.add("diagram-index");
      [...t.querySelectorAll("tbody tr")].forEach((tr, i) => {
        const td = tr.children[where];
        td.className = "num";
        td.innerHTML = `<a href="#diagram-${i + 1}"><span class="pg" data-target="diagram-${i + 1}">00</span></a>`;
      });
    }
  }
}

// Layout fitter. Simulates A4 pagination on the laid-out document and, when a
// screenshot or diagram block would be pushed to the next page leaving more than
// a quarter of the current page empty, reduces that block's images (never below
// 75 % of their normal size) so it fits. Headings, lead-in lines and workflow
// summary tables that must stay with the next block move with it.
function fitPages() {
  const MM = 96 / 25.4, H = 257 * MM, MIN = 0.75;
  const isSticky = (el) => el.matches("h2, h3, h4, p.subhead, p.leadin, table.meta")
    || (el.tagName === "P" && el.parentElement.tagName === "LI" && el.nextElementSibling && /^(UL|OL)$/.test(el.nextElementSibling.tagName));
  const sticksToPrev = (el) => el.tagName === "BLOCKQUOTE" || (el.tagName === "P" && el.previousElementSibling && el.previousElementSibling.matches("figure.diagram"));
  const collect = (el, out) => {
    for (const c of el.children) {
      if (c.matches("section.cover")) continue;
      if (c.matches("ol, ul") || (c.tagName === "DIV" && !c.matches(".keep, .pair, .toc"))) { collect(c, out); continue; }
      if (c.tagName === "LI" && [...c.children].some((x) => /^(P|UL|OL|FIGURE|DIV|TABLE|BLOCKQUOTE)$/.test(x.tagName))) { collect(c, out); continue; }
      if (c.tagName === "TABLE" && !c.matches(".meta")) { for (const tr of c.querySelectorAll("tbody tr")) out.push(tr); continue; }
      out.push(c);
    }
    return out;
  };
  const media = (el) => [...el.querySelectorAll("img, figure.diagram svg")];
  const shrinkable = (el) => media(el).length && !el.dataset.fitted;
  const simulate = () => {
    const items = collect(document.body, []);
    const y = (el) => el.getBoundingClientRect().top + window.scrollY;
    const yb = (el) => el.getBoundingClientRect().bottom + window.scrollY;
    let start = null, pages = 1;
    for (let i = 0; i < items.length; i++) {
      const it = items[i];
      if (start === null) { start = y(it); pages = 2; continue; } // page 1 is the cover
      if (it.matches("h2.newpage") && y(it) > start) { start = y(it); pages++; continue; }
      if (yb(it) - start <= H + 1) continue;
      const tall = yb(it) - y(it);
      if (/^(P|LI|PRE)$/.test(it.tagName) && tall > 40) { while (yb(it) - start > H) { start += H; pages++; } continue; }
      let k = i;
      while (k > 0 && (isSticky(items[k - 1]) || sticksToPrev(items[k]))) k--;
      const top = y(items[k]), slack = start + H - top;
      if (slack > 0.25 * H && shrinkable(it)) return { it, need: yb(it) - top - slack };
      start = top; pages++;
      while (yb(it) - start > H) { start += H; pages++; }
    }
    return { pages };
  };
  let shrunk = 0, r;
  for (let guard = 0; guard < 120; guard++) {
    r = simulate();
    if (!r.it) break;
    const els = media(r.it);
    const side = r.it.matches(".pair");
    const mh = side ? Math.max(...els.map((e) => e.getBoundingClientRect().height)) : els.reduce((a, e) => a + e.getBoundingClientRect().height, 0);
    const f = 1 - (r.need + 4) / mh;
    r.it.dataset.fitted = "1";
    if (f < MIN || f >= 1) continue;
    for (const e of els) {
      const b = e.getBoundingClientRect();
      e.style.width = `${b.width * f}px`; e.style.height = `${b.height * f}px`;
      const fig = e.closest("figure.shot"); if (fig && fig.style.width) fig.style.width = `${b.width * f}px`;
    }
    shrunk++;
  }
  return { shrunk, predictedPages: r.pages };
}

// Page number of every linked destination, read from the PDF's own named
// destinations (Chrome writes them as plain objects; no PDF library needed).
function pdfDestPages(buf) {
  const d = buf.toString("latin1");
  const objs = new Map();
  for (const m of d.matchAll(/(\d+) 0 obj([\s\S]*?)endobj/g)) {
    const body = m[2]; const st = body.indexOf("stream");
    objs.set(+m[1], st < 0 ? body : body.slice(0, st));
  }
  const pages = [];
  const walk = (n) => {
    const o = objs.get(n);
    if (/\/Type \/Pages/.test(o)) for (const k of o.match(/\/Kids \[([^\]]*)\]/)[1].matchAll(/(\d+) 0 R/g)) walk(+k[1]);
    else pages.push(n);
  };
  walk(+d.match(/\/Type \/Catalog[\s\S]*?\/Pages (\d+) 0 R/)[1]);
  const dm = d.match(/\/Dests (\d+) 0 R/);
  const map = {};
  if (dm) for (const m of objs.get(+dm[1]).matchAll(/\/([^\s/[\]]+)\s*\[(\d+) 0 R \/XYZ/g)) map[decodeURIComponent(m[1].replace(/#([0-9A-Fa-f]{2})/g, "%$1"))] = pages.indexOf(+m[2]) + 1;
  return { map, count: pages.length };
}

// ---------------------------------------------------------------- build
const MIN_DIAGRAM_TEXT_PT = 7;
const out = path.join(root, "pdf");
fs.mkdirSync(out, { recursive: true });
const browser = await puppeteer.launch({ headless: true, args: ["--no-sandbox", "--allow-file-access-from-files"] });
let failures = 0;
// Optional: build only the named manual folders, e.g. `node build-pdf.mjs 04-diji-at-work`.
const only = process.argv.slice(2);
// Manuals whose folder is not in this checkout are skipped.
for (const [dir, title] of MANUALS.filter(([d]) => (!only.length || only.includes(d)) && fs.existsSync(path.join(root, d)))) {
  const { html, version, classification } = render(dir, title);
  const tmp = path.join(root, dir, ".print.html");
  fs.writeFileSync(tmp, html);
  const page = await browser.newPage();
  // Lay out at the printed text width so the fitter measures what will be printed.
  await page.setViewport({ width: Math.round((210 - 36) * 96 / 25.4), height: 1100 });
  await page.emulateMediaType("print");
  await page.goto(pathToFileURL(tmp).href, { waitUntil: "networkidle0" });
  const { report: diagrams, trimmed } = await page.evaluate(async (newPageSections) => {
    const MM = 96 / 25.4;              // CSS px per mm
    const SCALE = 150 / 1440;          // mm per screenshot pixel (desktop)
    const MAX_FIG_MM = 125, MAX_W_MM = 160, PHONE_W_MM = 58;
    await Promise.all([...document.images].map((i) => (i.complete ? null : new Promise((r) => { i.onload = i.onerror = r; }))));

    for (const h of document.querySelectorAll("h3")) if (/^e\d+-/.test(h.id)) h.classList.add("wf");
    for (const h of document.querySelectorAll("h2")) if (newPageSections.includes(h.id)) h.classList.add("newpage");
    // The first paragraph after the title is the manual's one-line introduction.
    const firstP = [...document.querySelectorAll("body > p")].find((p) => /by Dijital Team:/.test(p.textContent)); if (firstP) firstP.classList.add("intro");
    // Key/value tables with an empty header row (| | |) are "meta" tables.
    for (const t of document.querySelectorAll("table")) {
      const ths = [...t.querySelectorAll("thead th")];
      if (ths.length === 2 && ths.every((th) => !th.textContent.trim())) { t.classList.add("meta"); t.querySelector("thead").remove(); }
    }

    // Bold-only paragraphs act as sub-headings; short lines ending in ":" lead into what follows.
    for (const p of document.querySelectorAll("p")) {
      const t = p.textContent.trim();
      if (p.children.length === 1 && p.firstElementChild.tagName === "STRONG" && p.firstElementChild.textContent.trim() === t) p.classList.add("subhead");
      else if (t.endsWith(":") && t.length < 220) p.classList.add("leadin");
    }
    // A workflow heading always stays with its summary table.
    for (const h of document.querySelectorAll("h3.wf")) {
      const t = h.nextElementSibling;
      if (t && t.tagName === "TABLE") { const k = document.createElement("div"); k.className = "keep"; h.before(k); k.append(h, t); }
    }

    // Mermaid diagrams: render, then caption with the diagram's own title.
    mermaid.initialize({
      startOnLoad: false, theme: "base", securityLevel: "strict",
      flowchart: { htmlLabels: false, curve: "basis", useMaxWidth: true, wrappingWidth: 190, rankSpacing: 34, nodeSpacing: 28, padding: 10 },
      state: { useMaxWidth: true },
      themeVariables: {
        fontFamily: "Helvetica Neue, Helvetica, Arial, sans-serif", fontSize: "13px",
        primaryColor: "#fff8ef", primaryBorderColor: "#c9431d", primaryTextColor: "#24140f",
        lineColor: "#8a6a5c", secondaryColor: "#fde3cf", tertiaryColor: "#ffffff",
        noteBkgColor: "#fffbe6", noteBorderColor: "#c78300", titleColor: "#8f2417",
      },
    });
    let d = 0; const report = [];
    const DIAGRAM_MM_PER_UNIT = 0.245, DIAGRAM_MAX_W_MM = 168, DIAGRAM_MAX_H_MM = 205;
    for (const code of [...document.querySelectorAll("pre > code.language-mermaid")]) {
      const src = code.textContent;
      const title = (src.match(/^\s*title:\s*(.+)$/m) || [, "Diagram"])[1].trim();
      try { await mermaid.parse(src); } catch (e) { throw new Error(`Mermaid diagram "${title}" does not parse: ${e.message || e}`); }
      const { svg } = await mermaid.render(`mmd${++d}`, src.replace(/^---[\s\S]*?---\s*/, ""));
      const f = document.createElement("figure"); f.className = "diagram";
      f.innerHTML = svg;
      const el = f.querySelector("svg");
      const vb = el.viewBox.baseVal;
      // One consistent print scale for every diagram (13 px Mermaid text prints at about 9 pt),
      // reduced only when a diagram is wider or taller than the page allows.
      const k = Math.min(DIAGRAM_MM_PER_UNIT, DIAGRAM_MAX_W_MM / vb.width, DIAGRAM_MAX_H_MM / vb.height);
      const wmm = vb.width * k, hmm = vb.height * k;
      el.style.width = `${wmm * MM}px`; el.style.height = `${hmm * MM}px`; el.style.maxWidth = "100%";
      el.removeAttribute("height");
      f.id = `diagram-${d}`;
      report.push({ n: d, title, textPt: +(13 * k * 72 / 25.4).toFixed(1), wmm: Math.round(wmm), hmm: Math.round(hmm) });
      const c = document.createElement("figcaption"); c.textContent = `Diagram ${d}. ${title}`;
      f.append(c);
      code.parentElement.replaceWith(f);
    }

    // Presentation trim for the PDF only (the PNG files are not changed): remove an empty
    // band at the bottom of a screenshot, such as the unused part of a short page or an
    // empty state. The application sidebar, if present, is ignored when looking for content.
    let trimmed = 0;
    for (const img of [...document.images]) {
      const w = img.naturalWidth, h = img.naturalHeight;
      if (w < 900 || h < 300) continue;
      const c = document.createElement("canvas"); c.width = w; c.height = h;
      const g = c.getContext("2d"); g.drawImage(img, 0, 0);
      const d = g.getImageData(0, 0, w, h).data;
      const px = (x, y) => (y * w + x) * 4;
      const mid = px(10, Math.floor(h / 2));
      const sidebar = d[mid] > 110 && d[mid + 1] < 90 && d[mid + 2] < 80;
      const x0 = sidebar ? Math.ceil(w * 0.185) : 0;
      let yc = h - 1;
      for (let y = h - 2; y > 0; y--) {
        let diff = 0;
        for (let x = x0; x < w; x += 2) {
          const a = px(x, y), b = px(x, y + 1);
          diff = Math.max(diff, Math.abs(d[a] - d[b]) + Math.abs(d[a + 1] - d[b + 1]) + Math.abs(d[a + 2] - d[b + 2]));
          if (diff > 18) break;
        }
        if (diff > 18) { yc = y; break; }
      }
      let nh = Math.min(h, yc + 36);
      // A small footer under a large empty band (for example the portal's closing line):
      // look for the empty band above the bottom content and stop the crop above it.
      const rowDiff = (y) => {
        let diff = 0;
        for (let x = x0; x < w; x += 2) {
          const a = px(x, y), b = px(x, y + 1);
          diff = Math.max(diff, Math.abs(d[a] - d[b]) + Math.abs(d[a + 1] - d[b + 1]) + Math.abs(d[a + 2] - d[b + 2]));
          if (diff > 18) break;
        }
        return diff;
      };
      if (yc > h * 0.85) {
        let y = yc, run = 0, bandEnd = -1;
        for (; y > h * 0.08; y--) {
          if (rowDiff(y) > 18) { if (run > h * 0.3) { bandEnd = y; break; } run = 0; } else run++;
        }
        if (bandEnd > 0) nh = Math.min(h, bandEnd + 36);
      }
      // Mostly empty screens (for example "access required" messages): if the first content
      // below the top bar starts far down, start the crop just above that content instead.
      const bar = Math.round(h * 0.08);
      let yt = bar;
      for (let y = bar + 4; y < nh - 1; y++) {
        let diff = 0;
        for (let x = x0; x < w; x += 2) {
          const a = px(x, y), b = px(x, y + 1);
          diff = Math.max(diff, Math.abs(d[a] - d[b]) + Math.abs(d[a + 1] - d[b + 1]) + Math.abs(d[a + 2] - d[b + 2]));
          if (diff > 18) break;
        }
        if (diff > 18) { yt = y; break; }
      }
      const top = yt - bar > h * 0.25 ? Math.max(0, yt - 40) : 0;
      if (nh - top > h * 0.85) continue;
      const o = document.createElement("canvas"); o.width = w; o.height = nh - top;
      o.getContext("2d").drawImage(c, 0, top, w, nh - top, 0, 0, w, nh - top);
      img.src = o.toDataURL("image/png");
      await img.decode();
      trimmed++;
    }
    report.trimmed = trimmed;

    let n = 0;
    const figure = (img) => {
      const w = img.naturalWidth, h = img.naturalHeight;
      // Annotated close-ups are crops of a full window, so they print larger than full-window captures.
      const scale = /annotated\//.test(img.dataset.src || "") ? 150 / 1000 : SCALE;
      let wmm = w < 600 && h / w > 1.5 ? PHONE_W_MM : Math.min(w * scale, MAX_W_MM);
      let hmm = wmm * h / w;
      if (hmm > MAX_FIG_MM) { wmm = wmm * MAX_FIG_MM / hmm; hmm = MAX_FIG_MM; }
      img.style.width = `${wmm * MM}px`; img.style.height = `${hmm * MM}px`;
      img.removeAttribute("title");
      const f = document.createElement("figure"); f.className = "shot";
      f.style.width = `${wmm * MM}px`;
      const c = document.createElement("figcaption"); c.textContent = `Figure ${++n}. ${img.alt}`;
      f.id = `figure-${n}`;
      f.append(img, c);
      return f;
    };
    // Paragraphs that contain only images become one figure, or a side-by-side pair/row.
    for (const p of [...document.querySelectorAll("p")]) {
      const imgs = [...p.querySelectorAll("img")];
      if (!imgs.length || p.textContent.trim()) continue;
      const figs = imgs.map(figure);
      if (figs.length === 1) { p.replaceWith(figs[0]); continue; }
      // Lay out in rows of two; each figure shares the row width.
      const frag = document.createDocumentFragment();
      for (let i = 0; i < figs.length; i += 2) {
        const row = document.createElement("div"); row.className = "pair";
        for (const f of figs.slice(i, i + 2)) { f.style.width = ""; row.append(f); }
        frag.append(row);
      }
      p.replaceWith(frag);
    }
    // Keep each figure on the same page as the short instruction directly above it.
    for (const f of [...document.querySelectorAll("figure.shot:not(.pair figure), .pair")]) {
      if (f.parentElement.classList.contains("keep")) continue;
      const prev = f.previousElementSibling;
      if (!prev || !["P", "UL", "OL", "H3", "H4", "TABLE", "BLOCKQUOTE"].includes(prev.tagName)) continue;
      if (prev.getBoundingClientRect().height > 70 * MM) continue;
      const k = document.createElement("div"); k.className = "keep";
      prev.before(k); k.append(prev, f);
      // A heading directly above the pair belongs with it too.
      const pp = k.previousElementSibling;
      if (pp && /^H[34]$/.test(pp.tagName)) k.prepend(pp);
    }
    return { report, trimmed };
  }, NEW_PAGE_SECTIONS);
  const weak = diagrams.filter((x) => x.textPt < MIN_DIAGRAM_TEXT_PT);
  for (const x of weak) console.warn(`  WARN diagram ${x.n} "${x.title}" prints with ${x.textPt} pt text (minimum ${MIN_DIAGRAM_TEXT_PT} pt): simplify or split it`);
  if (process.env.DIAGRAM_REPORT) for (const x of diagrams) console.log(`  diagram ${x.n}: ${x.textPt} pt, ${x.wmm}x${x.hmm} mm, ${x.title}`);
  await page.evaluate(buildNavigation);
  const fitted = await page.evaluate(fitPages);
  const pdfOptions = {
    format: "A4", printBackground: true, outline: true, tagged: true, displayHeaderFooter: true,
    headerTemplate: `<div style="font-family:Helvetica,Arial,sans-serif;font-size:7pt;color:#76584c;width:100%;padding:0 18mm;display:flex;justify-content:space-between;"><span>${title} - User Manual</span><span>DijiOne</span></div>`,
    footerTemplate: `<div style="font-family:Helvetica,Arial,sans-serif;font-size:7pt;color:#76584c;width:100%;padding:0 18mm;display:flex;justify-content:space-between;"><span>Version ${version} | ${classification} | by Dijital Team</span><span>Page <span class="pageNumber"></span> of <span class="totalPages"></span></span></div>`,
    margin: { top: "20mm", bottom: "20mm", left: "18mm", right: "18mm" },
  };
  // Pass 1: print, then read the page of every contents entry and diagram.
  const first = pdfDestPages(Buffer.from(await page.pdf(pdfOptions)));
  const missing = await page.evaluate((map) => {
    const miss = [];
    for (const s of document.querySelectorAll(".pg[data-target]")) {
      const n = map[s.dataset.target];
      if (n) s.textContent = String(n); else miss.push(s.dataset.target);
    }
    return miss;
  }, first.map);
  // Pass 2: the final PDF. Numbers replace same-width placeholders, so the layout does not move.
  const finalBuf = Buffer.from(await page.pdf(pdfOptions));
  fs.writeFileSync(path.join(out, pdfName(dir)), finalBuf);
  const second = pdfDestPages(finalBuf);
  const moved = Object.keys(first.map).filter((k) => first.map[k] !== second.map[k]);
  if (missing.length || moved.length) { failures++; console.error(`  ERROR ${dir}: page numbers ${missing.length ? "missing for " + missing.join(", ") : ""}${moved.length ? " moved for " + moved.join(", ") : ""}`); }
  await page.close();
  fs.unlinkSync(tmp);
  console.log(`built ${pdfName(dir)}: ${second.count} pages, ${diagrams.length} diagrams, ${fitted.shrunk} blocks fitted, ${trimmed} screenshots trimmed (predicted ${fitted.predictedPages} pages)`);
}
await browser.close();
if (failures) { console.error(`FAILED: ${failures} manual(s) with page-number problems`); process.exit(1); }
