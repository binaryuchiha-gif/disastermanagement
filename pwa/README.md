# ResQFlow-X PWA (Phase 1B / 5)

Offline-first evacuation app: MapLibre GL vector basemap from a single
**PMTiles** file, risk overlays from the on-device model, offline routing,
snapping, turn-by-turn, SOS queue, and i18n (English/Tamil/Hindi).

## What is verified vs UNVERIFIED

**Verified in the dev sandbox + CI core job (plain `node`, no npm):**
- All offline *logic* modules: `geo.js`, `snapping.js` (KD-tree), `turnbyturn.js`
  (instructions + off-route), `routing.js` (Dijkstra + uncertainty cost),
  `i18n.js`, `sync.js` (offline queue, idempotent flush, LWW conflict).
  See `scripts/node_smoke.mjs` (12 assertions).
- **Python↔JS routing parity**: 60 cases, max cost diff **0** (`scripts/parity_check.mjs`).
- **Python↔JS risk-model parity**: max diff **1.67e-16** over 200 samples
  (`risk_model/export_js.py`).

**UNVERIFIED (needs `npm install`, blocked in the sandbox) — run locally:**
```bash
cd pwa
npm install
npm run test        # Vitest unit tests
npm run build
npm run preview     # serve
npx playwright install --with-deps chromium
npm run test:e2e    # offline acceptance (airplane-mode reload)
```
- MapLibre + PMTiles rendering, service-worker Range handling (`public/sw.js`),
  the download-offline-map flow, and the Playwright offline acceptance test.
- Build the basemap first: `bash scripts/build_tiles.sh` (needs a Geofabrik
  extract + Planetiler/tilemaker). Self-host fonts (`public/fonts/`) and sprites
  (`public/sprites/`) — missing glyphs cause blank labels.

## Offline acceptance test (the Phase-1B goal)
Cold load online → "Download offline map" → airplane mode → reload → map,
overlays, search, routing, and SOS still work. Encoded in
`tests/offline.e2e.spec.js`.

## Metrics to report for H5 (UNVERIFIED — measure on a real phone)
Tile size, cold load time, FPS with the full risk layer, full-network re-score
ms, route latency ms, GPS battery impact. Commands in `docs/REPRODUCE.md`.

## Attribution
Basemap data © OpenStreetMap contributors (ODbL).
