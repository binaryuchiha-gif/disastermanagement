import { defineConfig, devices } from "@playwright/test";

// UNVERIFIED in the dev sandbox (needs npm). Mid-range phone emulation for the
// offline acceptance test.
export default defineConfig({
  testDir: "./tests",
  testMatch: /.*\.e2e\.spec\.js/,
  timeout: 60000,
  use: {
    baseURL: "http://localhost:4173",
    ...devices["Pixel 5"],
  },
  webServer: {
    command: "npm run build && npm run preview -- --port 4173",
    url: "http://localhost:4173",
    reuseExistingServer: true,
    timeout: 120000,
  },
});
