# Reproduce — exact commands

Two tracks: (A) the **SYNTHETIC** results that run with zero internet and only
Python stdlib + pytest (what this repo was built against), and (B) the
**REAL-DATA / full-stack** steps that need internet + `pip`/`npm` and that you
run locally. UNVERIFIED items are flagged.

---
## A. Runs anywhere (stdlib only) — verified
```bash
make test            # 67 stdlib tests (routing, sim, model, stats, pipeline, reliability)
make demo-graph      # SYNTHETIC city graph
make experiments     # 33-seed sweep -> results/*.csv + figures + manifest  (~7 min)
python -m experiments.check_determinism --seed 1234
python -m routing.benchmark --sizes 20 30 45 --repeats 5
python -m risk_model.train --seed 0 --nx 25         # H1 metrics
python -m risk_model.export_js --check-parity        # PY<->JS model parity

# JS offline logic (plain node, no npm):
cd pwa && node scripts/node_smoke.mjs
python -m scripts.export_parity_vectors && node pwa/scripts/parity_check.mjs results/parity_vectors_SYNTHETIC.json
```

---
## B. Real data + full stack (needs internet + pip/npm) — UNVERIFIED

### B1. Python environment
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### B2. Build the REAL Chennai graph (OSM + SRTM DEM)
```bash
# 1) OSM extract (Geofabrik), clip to study bbox:
#    https://download.geofabrik.de/asia/india/southern-zone-latest.osm.pbf
osmium extract -b 80.18,12.93,80.25,13.02 southern-zone-latest.osm.pbf \
  -o data/raw/chennai.osm.pbf
# 2) SRTM DEM GeoTIFF covering the bbox -> data/raw/srtm_chennai.tif
#    (e.g. from https://dwtkns.com/srtm30m/ or earthdata; public domain)
# 3) Build the graph:
python -m pipeline.build_real_graph --config experiments/configs/chennai.yaml
```

### B3. Train the REAL model (LightGBM/RF + SHAP + MLflow)
```bash
# Prepare a labeled real dataset at data/processed/real_dataset.parquet first
# (features from B2 + rainfall + ground-truth flood labels from SAR/inundation
# maps — see docs/DATA_CARD.md). Then:
python -m risk_model.train_lib --config experiments/configs/model.yaml --real
mlflow ui    # view tracked runs
```

### B4. Build the offline PMTiles basemap
```bash
bash scripts/build_tiles.sh      # Planetiler or tilemaker -> pwa/public/tiles/*.pmtiles
# self-host fonts (glyph PBFs) under pwa/public/fonts/ and sprites under pwa/public/sprites/
```

### B5. PWA + offline acceptance (Playwright)
```bash
cd pwa
npm install
npm run test                     # Vitest unit tests
npm run build && npm run preview &
npx playwright install --with-deps chromium
npm run test:e2e                 # cold load -> airplane mode -> reload acceptance
```

### B6. Backend
```bash
pip install -r requirements.txt
uvicorn backend.app:app --reload     # OpenAPI at http://localhost:8000/docs
# or: docker compose up
```

### B7. Phone benchmarks for H5 (the main UNVERIFIED numbers)
On a mid-range Android phone (Chrome), with the app installed offline:
- **Tile size:** `ls -lh pwa/public/tiles/*.pmtiles`
- **Cold load time:** DevTools Performance trace, airplane mode, reload.
- **FPS with full risk layer:** DevTools FPS meter while panning at zoom 12–14.
- **Full-network re-score ms:** time `scoreEdges()` over all edges (log to console).
- **Route latency ms:** already logged in the "why this route" panel.
- **GPS battery impact:** Android Battery usage over a 15-min tracked session.
Record these in `docs/PERFORMANCE_BUDGET.md` (replace the UNVERIFIED rows).

---
## What to replace in the paper once real results exist
- `docs/paper/paper.md`: every table/figure marked **(SYNTHETIC)** → rerun A/B on
  real data and swap in the REAL numbers; move SYNTHETIC results to an appendix
  labeled "methodology validation on synthetic data".
- `docs/MODEL_CARD.md`: fill the REAL metric columns from B3.
- `docs/PERFORMANCE_BUDGET.md`: fill phone rows from B7.
- `docs/DATA_CARD.md`: set the real datasets' dates/versions/licenses.
