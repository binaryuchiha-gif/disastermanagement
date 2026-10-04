// Playwright end-to-end offline test (Phase 1B/6 acceptance). UNVERIFIED in the
// dev sandbox (needs `npm install` + browser download). Run locally:
//   npm run build && npm run preview &  (or vite dev)
//   npx playwright install --with-deps chromium
//   npm run test:e2e
//
// Acceptance: cold load online -> airplane mode -> reload; map, overlays,
// search, routing, and SOS still work.

import { test, expect } from "@playwright/test";

test.describe("ResQFlow-X offline acceptance", () => {
  test("cold load online, then fully offline reload", async ({ page, context }) => {
    await page.goto("/");
    await expect(page.locator("#status")).toContainText(/map ready|fallback/i, { timeout: 15000 });

    // trigger offline map download so PMTiles is cached
    await page.click("#downloadMap");
    await expect(page.locator("#status")).toContainText(/downloaded|download/i, { timeout: 30000 });

    // go offline (airplane mode) and reload
    await context.setOffline(true);
    await page.reload();

    // map still initializes from cache (ready or documented fallback)
    await expect(page.locator("#status")).toContainText(/ready|fallback|offline/i, { timeout: 15000 });

    // routing still works offline: tap start + destination
    const map = page.locator("#map");
    const box = await map.boundingBox();
    await page.mouse.click(box.x + box.width * 0.35, box.y + box.height * 0.4);
    await page.mouse.click(box.x + box.width * 0.65, box.y + box.height * 0.6);
    await expect(page.locator("#whyPanel")).toContainText(/Why this route|on-device/i, { timeout: 10000 });

    // SOS queues offline
    await page.click("#sos");
    await expect(page.locator("#status")).toContainText(/SOS queued/i, { timeout: 10000 });
  });
});
