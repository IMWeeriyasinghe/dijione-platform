import os from "node:os";
import path from "node:path";
import { defineConfig, devices } from "@playwright/test";

// The real app against a real talent-api on a throwaway SQLite database.
const API_PORT = 8102;
export const STATE_FILE = path.join(os.tmpdir(), `dijione-talent-e2e-${API_PORT}.json`);

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  timeout: 90_000,
  retries: process.env.CI ? 1 : 0,
  use: { baseURL: "http://localhost:3100", ...devices["Desktop Chrome"] },
  webServer: [
    {
      command: `\"${process.env.E2E_PYTHON ?? "python"}\" tests/e2e_server.py ${API_PORT}`,
      cwd: "../talent-api",
      env: { E2E_STATE: STATE_FILE },
      url: `http://127.0.0.1:${API_PORT}/health`,
      reuseExistingServer: false,
      timeout: 60_000,
    },
    {
      command: "npm run dev",
      env: { TALENT_API_URL: `http://127.0.0.1:${API_PORT}` },
      url: "http://localhost:3100/access",
      reuseExistingServer: false,
      timeout: 180_000,
    },
  ],
});
