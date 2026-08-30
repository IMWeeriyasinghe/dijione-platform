#!/usr/bin/env node
/**
 * Starts every DijiOne service for local development with one command:
 *
 *   npm run dev:all
 *
 * Backend services (Python/FastAPI) run via the shared repo-root .venv;
 * frontend apps (Next.js) run via their own npm workspace `dev` script.
 * See docs/platform/local-development.md for the full port list and
 * troubleshooting notes.
 */

const { spawn } = require("node:child_process");
const path = require("node:path");
const fs = require("node:fs");

const REPO_ROOT = path.resolve(__dirname, "..");
const isWindows = process.platform === "win32";
const venvPython = path.join(
  REPO_ROOT,
  ".venv",
  isWindows ? "Scripts" : "bin",
  isWindows ? "python.exe" : "python"
);
const pythonCmd = fs.existsSync(venvPython) ? venvPython : "python";

const services = [
  { name: "platform-api", color: "\x1b[36m", cwd: "apps/platform-api", cmd: pythonCmd, args: ["-m", "uvicorn", "app.main:app", "--port", "8000", "--reload"] },
  { name: "admin-api", color: "\x1b[35m", cwd: "apps/admin-api", cmd: pythonCmd, args: ["-m", "uvicorn", "app.main:app", "--port", "8001", "--reload"] },
  { name: "talent-api", color: "\x1b[33m", cwd: "apps/talent-api", cmd: pythonCmd, args: ["-m", "uvicorn", "app.main:app", "--port", "8002", "--reload"] },
  { name: "birthday-api", color: "\x1b[32m", cwd: "apps/birthday-api", cmd: pythonCmd, args: ["-m", "uvicorn", "app.main:app", "--port", "8003", "--reload"] },
  { name: "spark-api", color: "\x1b[34m", cwd: "apps/spark-api", cmd: pythonCmd, args: ["-m", "uvicorn", "app.main:app", "--port", "8004", "--reload"] },
  { name: "shell-web", color: "\x1b[91m", cwd: "apps/shell-web", cmd: "npm", args: ["run", "dev"] },
  { name: "admin-web", color: "\x1b[95m", cwd: "apps/admin-web", cmd: "npm", args: ["run", "dev"] },
  { name: "talent-web", color: "\x1b[93m", cwd: "apps/talent-web", cmd: "npm", args: ["run", "dev"] },
  { name: "birthday-web", color: "\x1b[92m", cwd: "apps/birthday-web", cmd: "npm", args: ["run", "dev"] },
  // External-facing supplier portal (separate app, port 3006). Not proxied
  // through shell-web — it is reached directly by external supplier users.
  { name: "birthday-supplier-web", color: "\x1b[96m", cwd: "apps/birthday-supplier-web", cmd: "npm", args: ["run", "dev"] },
];

const RESET = "\x1b[0m";
const nameWidth = Math.max(...services.map((s) => s.name.length));

function prefix(service) {
  return `${service.color}[${service.name.padEnd(nameWidth)}]${RESET} `;
}

function pipe(stream, service, out) {
  let buffer = "";
  stream.on("data", (chunk) => {
    buffer += chunk.toString();
    const lines = buffer.split("\n");
    buffer = lines.pop();
    for (const line of lines) out.write(prefix(service) + line + "\n");
  });
}

const children = services.map((service) => {
  // `shell: true` is only needed to resolve `npm` -> `npm.cmd` on Windows;
  // applying it to the venv's absolute python.exe path breaks on Windows
  // when the repo path contains spaces (cmd.exe re-splits an unquoted
  // absolute path on its first space).
  const child = spawn(service.cmd, service.args, {
    cwd: path.join(REPO_ROOT, service.cwd),
    shell: isWindows && service.cmd === "npm",
    env: process.env,
  });
  pipe(child.stdout, service, process.stdout);
  pipe(child.stderr, service, process.stderr);
  child.on("exit", (code) => {
    process.stdout.write(prefix(service) + `exited with code ${code}\n`);
  });
  return child;
});

function shutdown() {
  for (const child of children) {
    if (!child.killed) child.kill();
  }
  process.exit(0);
}

process.on("SIGINT", shutdown);
process.on("SIGTERM", shutdown);
