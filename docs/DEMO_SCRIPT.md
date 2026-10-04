# 5-Minute Demo Script + Recording Checklist

A scripted demo that tells the story: online → airplane mode → flood scenario →
reroute after a blockage → SOS queued → reconnect & sync.

## Pre-demo setup (once, with internet)
```bash
# research side (works anywhere)
make experiments            # tables + figures in results/
# PWA side (needs npm + a basemap)
bash scripts/build_tiles.sh # pwa/public/tiles/study_area.pmtiles
cd pwa && npm install && npm run build && npm run preview
```
Open the app in Chrome on a phone (or Pixel-5 emulation in DevTools).

## The 5-minute flow
1. **(0:00) Online cold load.** Open the app. Show the muted basemap and the
   risk overlay. Point out the legend and attribution "© OpenStreetMap
   contributors". *Say:* "Risk colors come from a learned model running on the
   phone, not a server."
2. **(0:45) Scenario slider.** Drag rainfall mild → extreme. Edges recolor
   instantly. *Say:* "No network call — the model re-scores all edges on-device."
3. **(1:30) Pick a route.** Tap a start and a shelter. Show the **safest**
   (uncertainty-aware) route vs **fastest** (toggle method). Open the "why this
   route" panel (segment count, mean failure risk, on-device latency ms).
4. **(2:15) Airplane mode.** Enable it (or DevTools offline). *Say:* "Now there
   is no internet." Reload — the map, overlays, search, and routing still work
   from cache (service-worker Range cache for the PMTiles file).
5. **(3:00) Blockage + reroute.** Mark a road on the current route as blocked
   (tap-to-report / admin). The app detects the broken edge and **reroutes**
   automatically. Show the new path avoiding the blockage.
6. **(3:45) SOS queued offline.** Tap **SOS**. Status shows "SOS queued (will
   send when online)". *Say:* "<200-byte payload: location, battery, group size,
   a client UUID for idempotency — stored in IndexedDB."
7. **(4:15) Reconnect & sync.** Turn internet back on. The queued SOS and report
   flush to the backend; the server dedupes on the UUID. Show the admin stats
   count increment.
8. **(4:45) Close on honesty.** *Say:* "All of this ran on synthetic data in a
   no-internet build; every result is tagged SYNTHETIC, and the exact commands to
   run it on real Chennai data are in REPRODUCE.md."

## Recording checklist
- [ ] Screen recording at phone resolution (or Pixel-5 emulation).
- [ ] Network throttle indicator visible when toggling offline.
- [ ] DevTools FPS meter visible during the panning segment (for H5).
- [ ] Console open to show on-device re-score / route latency logs.
- [ ] A results/ figure (safety-time curve) shown at the end for the research claim.
- [ ] Audio narration matching the steps above; keep under 5:00.

## Fallback if no basemap is built
The app renders a documented minimal-fallback style and still does routing + SOS;
demo steps 3–7 all work without tiles. Say so explicitly on camera.
