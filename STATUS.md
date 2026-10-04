# STATUS

Live status of ResQFlow-X. Legend: ✅ done & tested here · 🟡 in progress ·
⚠️ UNVERIFIED (code written, needs local run) · ⛔ needs user input.

Last updated: Phase 0 complete, beginning execution.

## Environment facts (verified in sandbox)
- No internet (`INTEGRATIONS_ONLY`); `pip`/`npm` installs return HTTP 403.
- Available: Python 3.11 stdlib + `pytest 9.1.1`; Node v22 (needs `NODE_OPTIONS=`).
- NOT available: numpy, scipy, scikit-learn, networkx, lightgbm, matplotlib,
  pandas, hypothesis, OSMnx, FastAPI, MapLibre toolchain.
- Decision: research core is **pure stdlib**, genuinely run & tested here.
  Library-dependent variants are written + pinned + marked UNVERIFIED.

## Phase status
| Phase | Component | Status | Notes |
|-------|-----------|--------|-------|
| 0 | Audit & plan | ✅ | Repo was empty; greenfield. Report delivered & approved. |
| scaffold | Folders, README, STATUS, Make, CI, configs | ✅ | done |
| 3 | Routing algorithms (9) | ✅ | all 9 impl + 25 property tests green + benchmarks + complexity doc |
| 4 | Simulator + experiments + stats | ✅ | ABM sim + reverse-SSSP cache + 33-seed runner + Wilcoxon/Cliff's/Holm + SVG figures + robustness. H2/H3/H4 confirmed on SYNTHETIC data. |
| 2 | Feature pipeline + model + calibration + export | ✅ | stdlib GBT+logistic+baselines, spatial CV, isotonic/Platt, split-conformal (cov 0.918), perm-importance (hydrology-sensible), JS export + parity VERIFIED (1.67e-16). Lib path (LightGBM/SHAP/MLflow) UNVERIFIED. |
| 1 | OSM/DEM pipeline | ✅ (sim) / ⚠️ (real) | validate.py + compression + snap-test RUN in sandbox (100% SCC, 4.4x compress). build_real_graph.py (OSMnx+SRTM) UNVERIFIED. DATA_CARD done. |
| 1B | MapLibre/PMTiles PWA | ✅ (logic) / ⚠️ (map) | geo/snapping/turn-by-turn/routing/sync/i18n RUN+tested under node (12 smoke asserts). PY<->JS routing parity 0, model parity 1.67e-16. SW Range handler, MapLibre+PMTiles wiring, download flow, Playwright e2e written but UNVERIFIED (needs npm). |
| 5 | FastAPI backend + sync + admin + i18n | ✅ (reliability+sync+i18n) / ⚠️ (API) | reliability scorer RUN+tested + adversarial eval (precision>=0.9 @60% adv). sync.js + i18n (en/ta/hi) tested under node. FastAPI app, JWT, SQLite, Docker UNVERIFIED. Privacy note done. |
| 6 | Tests, CI, docs | ✅ | 67 stdlib tests + JS smoke + parity; CI core job green-by-design; ARCHITECTURE, DATA_CARD, MODEL_CARD, LIMITATIONS, ETHICS, PRIVACY, REPRODUCE, PERFORMANCE_BUDGET, ROUTING_COMPLEXITY. |
| 7 | Paper, demo, VIVA_QA | ✅ | paper draft (real SYNTHETIC numbers, contribution statement), DEMO_SCRIPT, VIVA_QA. |

## Needs user input ⛔
- Real `data/raw/` files (OSM extract + SRTM DEM) to run genuine Phase 1.
- Dependency provisioning (local `pip install -r requirements.txt`) to verify
  Phase 2 library models, Phase 5 backend, Phase 1B map stack.
- Phone benchmarks for H5 (cannot run on-device here).

## Unverified items (exact commands in docs/REPRODUCE.md)
- **Real geo pipeline** (`pipeline/build_real_graph`): needs internet + osmnx/
  rasterio. Cmd: `python -m pipeline.build_real_graph --config experiments/configs/chennai.yaml`
- **Library model path** (`risk_model/train_lib`): LightGBM/RF/SHAP/MLflow.
  Cmd: `pip install -r requirements.txt && python -m risk_model.train_lib --config experiments/configs/model.yaml --real`
- **PMTiles basemap**: `bash scripts/build_tiles.sh` (Planetiler/tilemaker + Geofabrik).
- **PWA rendering + offline e2e**: `cd pwa && npm install && npm run build && npm run test:e2e`.
- **FastAPI backend**: `pip install -r requirements.txt && uvicorn backend.app:app` or `docker compose up`.
- **Phone benchmarks (H5)**: tile size, cold load, FPS, re-score ms, battery —
  REPRODUCE.md §B7. These are the main missing numbers for the paper.

## What to replace in the paper once real results exist
Swap every (SYNTHETIC)-tagged table/figure for REAL-data reruns; fill MODEL_CARD
real columns; fill PERFORMANCE_BUDGET phone rows; move synthetic results to an
appendix. See REPRODUCE.md "What to replace in the paper".
