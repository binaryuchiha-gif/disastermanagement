# ResQFlow-X

**Uncertainty-aware, offline-first evacuation routing on a real city road network.**

ResQFlow-X researches whether *uncertainty-aware, risk-aware* evacuation routing —
driven by a learned road-failure model that runs fully offline on-device —
produces safer and faster evacuations than shortest-path and static-risk
baselines, and how robust it is when the model is wrong.

> ⚠️ **Life-critical disclaimer.** This is a research prototype. It is **not**
> a certified emergency tool. Routing advice can be wrong. See
> [`docs/ETHICS.md`](docs/ETHICS.md). Fail-safe behaviour is documented and
> enforced in code: when the risk model is unavailable or low-confidence, the
> system falls back to conservative routing and tells the user.

---

## Research question & hypotheses

> Does uncertainty-aware, risk-aware evacuation routing on a real city road
> network, driven by a learned road-failure model that runs fully offline
> on-device, produce safer and faster evacuations than shortest-path and
> static-risk baselines, and how robust is it when the model is wrong?

| ID | Hypothesis | Primary metric | Where tested |
|----|-----------|----------------|--------------|
| H1 | Learned risk beats hand-tuned/static risk at predicting road failure | ROC-AUC, PR-AUC, Brier, ECE | `risk_model/` |
| H2 | Uncertainty-aware costs reduce mid-route failures | % mid-route failures | `sim/` |
| H3 | Chance-constrained routing gives a controllable safety/time tradeoff | safety–time curve, monotonicity | `routing/`, `sim/` |
| H4 | Capacity/congestion-aware assignment reduces overload & tail times | 95th-pct time, overload count | `routing/`, `sim/` |
| H5 | Everything runs on a mid-range phone offline within a latency budget | re-score ms, route ms, size | `pwa/`, benchmarks |

---

## ⚠️ Environment & data status (read this first)

This repository was **developed inside a sealed sandbox with NO internet access
and NO package registry access** (`pip`/`npm` installs are blocked). Two
consequences drive the whole design:

1. **The research core is pure Python standard library + `pytest`.** No numpy,
   scipy, scikit-learn, networkx, lightgbm, matplotlib, or pandas are used in the
   runnable core. Everything the sandbox *can* run is **genuinely run and tested**
   — those results are real (on synthetic data).
2. **All geo/rainfall/flood data require the open internet**, which the sandbox
   lacks. So the runnable results use a **physics-informed SYNTHETIC city graph
   and SYNTHETIC flood labeler**. Every synthetic artifact is tagged `SYNTHETIC`
   in its filename, figure title, table caption, and docs.

Anything that needs an uninstallable library or real data is written in full,
accompanied by **pinned requirements and the exact command for you to run
locally**, and marked **`UNVERIFIED`** until you run it. See
[`STATUS.md`](STATUS.md) for the live breakdown and
[`docs/LIMITATIONS.md`](docs/LIMITATIONS.md).

**Nothing in this repo fabricates data, metrics, results, citations, or
on-device benchmarks.** Numbers I could not produce are labelled `UNVERIFIED`
with the command to reproduce them.

---

## Quick start (runs in the sandbox, no internet, no pip)

```bash
make test          # run the pure-stdlib test suite (routing, sim, model, stats)
make demo-graph    # generate a SYNTHETIC city graph + risk labels
make experiments   # reproduce every SYNTHETIC table & figure into results/
```

To work with **real data** and the **full ML/geo/map stack**, see
[`docs/REPRODUCE.md`](docs/REPRODUCE.md) for the exact local commands
(requires internet + `pip install -r requirements.txt`).

---

## Repository layout

```
pipeline/     Phase 1   OSM + DEM import, feature engineering (scripted, cached, seeded)
risk_model/   Phase 2   training, spatial CV, calibration, conformal, SHAP, export-to-JS
routing/      Phase 3   9 routing algorithms + property tests + benchmarks
sim/          Phase 4   agent-based evacuation simulator + experiment runner + stats
backend/      Phase 5   FastAPI + Pydantic + SQLite, OpenAPI, Docker
pwa/          Phase 1B/5  MapLibre + PMTiles, service worker, IndexedDB sync, i18n
experiments/  config-driven runs; `make experiments` -> results/ + manifest
results/      figures (SVG), tables (CSV/MD), run manifests
tests/        pytest + property tests (stdlib)
docs/         ARCHITECTURE, DATA_CARD, MODEL_CARD, LIMITATIONS, ETHICS, VIVA_QA, paper
legacy/       baseline prototype (comparison hook)
scripts/      helper scripts
```

## Attribution

Any map data in deployment is **© OpenStreetMap contributors** (ODbL). Elevation
from SRTM (NASA/USGS, public domain). See [`docs/DATA_CARD.md`](docs/DATA_CARD.md).

## License

Code: MIT (see `LICENSE`). Data artifacts follow their upstream licenses.
