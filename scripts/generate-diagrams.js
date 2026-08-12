#!/usr/bin/env node
/**
 * Regenerates every rendered PNG under docs/diagrams/rendered/ from the
 * Mermaid source files under docs/diagrams/source/.
 *
 * Mermaid (.mmd) files are the editable source of truth for all
 * architecture/workflow diagrams; the PNGs are a generated, reviewable
 * export and must never be hand-edited.
 *
 * Usage:  npm run diagrams   (from the repository root)
 */

const { spawnSync } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");

const REPO_ROOT = path.resolve(__dirname, "..");
const SOURCE_DIR = path.join(REPO_ROOT, "docs", "diagrams", "source");
const RENDERED_DIR = path.join(REPO_ROOT, "docs", "diagrams", "rendered");

const RENDER_ARGS = ["-w", "1600", "-s", "2", "-b", "white"];

function findMmdc() {
  const binName = process.platform === "win32" ? "mmdc.cmd" : "mmdc";
  // Search this project's own node_modules first, then walk up parent
  // directories (covers a shared/parent install like this repo's, e.g.
  // ../node_modules/.bin/mmdc), then fall back to PATH.
  let dir = REPO_ROOT;
  for (let i = 0; i < 5; i++) {
    const candidate = path.join(dir, "node_modules", ".bin", binName);
    if (fs.existsSync(candidate)) return candidate;
    const parent = path.dirname(dir);
    if (parent === dir) break;
    dir = parent;
  }
  return binName; // rely on PATH; spawnSync(..., {shell:true}) will resolve it
}

function main() {
  if (!fs.existsSync(SOURCE_DIR)) {
    console.error(`Source directory not found: ${SOURCE_DIR}`);
    process.exit(1);
  }
  fs.mkdirSync(RENDERED_DIR, { recursive: true });

  const mmdc = findMmdc();
  const sources = fs
    .readdirSync(SOURCE_DIR)
    .filter((f) => f.endsWith(".mmd"))
    .sort();

  if (sources.length === 0) {
    console.error(`No .mmd files found in ${SOURCE_DIR}`);
    process.exit(1);
  }

  console.log(`Rendering ${sources.length} diagram(s) with ${mmdc}\n`);

  const failures = [];
  for (const file of sources) {
    const input = path.join(SOURCE_DIR, file);
    const outputName = file.replace(/\.mmd$/, ".png");
    const output = path.join(RENDERED_DIR, outputName);

    process.stdout.write(`  ${file} -> rendered/${outputName} ... `);
    // Built as a single quoted command string (rather than an argv array)
    // because Windows + shell:true does not auto-quote array elements that
    // contain spaces (this repo's path does: "Diji Projects").
    const quote = (s) => `"${s}"`;
    const commandLine = [quote(mmdc), "-i", quote(input), "-o", quote(output), ...RENDER_ARGS].join(" ");
    const result = spawnSync(commandLine, { shell: true, encoding: "utf-8" });

    if (result.status === 0 && fs.existsSync(output)) {
      console.log("ok");
    } else {
      console.log("FAILED");
      failures.push({ file, error: (result.stderr || result.stdout || "unknown error").trim() });
    }
  }

  console.log("");
  console.log(`${sources.length - failures.length}/${sources.length} diagrams rendered successfully.`);

  if (failures.length > 0) {
    console.log("\nFailed diagrams:");
    for (const f of failures) {
      console.log(`  - ${f.file}`);
      console.log(`    ${f.error.split("\n").slice(0, 5).join("\n    ")}`);
    }
    process.exit(1);
  }
}

main();
